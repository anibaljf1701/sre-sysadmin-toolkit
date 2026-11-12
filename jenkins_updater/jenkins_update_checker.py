#!/usr/bin/env python3
"""
Jenkins Update Checker (EC2 / Systemd environments)
Discovers OS/Jenkins Core and Plugin updates, writes an approval manifest,
and notifies the SRE team via email only when updates are available.
Uses 100% Python Standard Library.
"""

import base64
from datetime import datetime, timezone
from email.message import EmailMessage
import json
import os
from pathlib import Path
import shutil
import smtplib
import subprocess
import sys
import urllib.error
import urllib.request


def get_env(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(key, default)
    if required and not val:
        print(f"[ERROR] Variable de entorno requerida no definida: {key}", file=sys.stderr)
        sys.exit(1)
    return val or ""


def jenkins_api_get(endpoint: str, base_url: str, user: str, token: str) -> dict:
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    auth_str = base64.b64encode(f"{user}:{token}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth_str}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_system_updates() -> dict:
    """Detecta actualizaciones de paquetes del SO y de Jenkins Core (apt o dnf/yum)."""
    core_update = None
    os_packages = []

    if shutil.which("apt-get"):
        subprocess.run(["apt-get", "update", "-qq"], check=False)
        res = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in res.stdout.splitlines():
            if "/" not in line or line.startswith("Listing"):
                continue
            pkg_name = line.split("/")[0].strip()
            version_info = line.split()[1] if len(line.split()) > 1 else "unknown"
            if pkg_name == "jenkins":
                core_update = {"package": "jenkins", "target_version": version_info}
            else:
                os_packages.append({"package": pkg_name, "target_version": version_info})

    elif shutil.which("dnf") or shutil.which("yum"):
        pkg_mgr = "dnf" if shutil.which("dnf") else "yum"
        res = subprocess.run(
            [pkg_mgr, "check-update", "-q"],
            capture_output=True,
            text=True,
            check=False,
        )
        # Código 100 indica actualizaciones disponibles en dnf/yum
        if res.returncode == 100:
            for line in res.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    pkg_name = parts[0].split(".")[0]
                    version_info = parts[1]
                    if pkg_name == "jenkins":
                        core_update = {"package": "jenkins", "target_version": version_info}
                    else:
                        os_packages.append({"package": pkg_name, "target_version": version_info})

    return {"core": core_update, "os_packages": os_packages}


def check_plugin_updates(base_url: str, user: str, token: str) -> list[dict]:
    """Consulta la API de Jenkins para listar plugins instalados con actualizaciones pendientes."""
    # Trigger refresh silencioso del Update Center
    try:
        auth_str = base64.b64encode(f"{user}:{token}".encode("utf-8")).decode("ascii")
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/pluginManager/checkUpdatesServer",
            method="POST",
            headers={"Authorization": f"Basic {auth_str}"},
        )
        urllib.request.urlopen(req, timeout=30)
    except Exception:
        pass

    plugins_data = jenkins_api_get("pluginManager/api/json?depth=1", base_url, user, token)
    updates_available = []

    for plugin in plugins_data.get("plugins", []):
        if plugin.get("hasUpdate"):
            updates_available.append({
                "name": plugin.get("shortName"),
                "display_name": plugin.get("longName"),
                "current_version": plugin.get("version"),
                "enabled": plugin.get("enabled", True),
            })

    return sorted(updates_available, key=lambda x: x["name"])


def send_email_report(subject: str, body: str) -> None:
    domain = get_env("COMPANY_DOMAIN", "example.com")
    recipient = get_env("ALERT_RECIPIENT", f"sre-team@{domain}")
    smtp_host = get_env("SMTP_HOST", required=True)
    smtp_port = int(get_env("SMTP_PORT", "587"))
    smtp_user = get_env("SMTP_USER", required=True)
    smtp_pass = get_env("SMTP_PASSWORD", required=True)
    sender = get_env("SMTP_FROM", f"jenkins-ops@{domain}")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


def main() -> None:
    jenkins_url = get_env("JENKINS_URL", "http://localhost:8080")
    jenkins_user = get_env("JENKINS_USER", required=True)
    jenkins_token = get_env("JENKINS_API_TOKEN", required=True)
    manifest_path = Path(get_env("MANIFEST_PATH", "/var/lib/jenkins-updater/pending_updates.json"))

    sys_updates = check_system_updates()
    plugin_updates = check_plugin_updates(jenkins_url, jenkins_user, jenkins_token)

    has_core = sys_updates["core"] is not None
    has_os = len(sys_updates["os_packages"]) > 0
    has_plugins = len(plugin_updates) > 0

    # Regla estricta: Si no hay actualizaciones, no generar reporte ni manifiesto
    if not (has_core or has_os or has_plugins):
        manifest_path.unlink(missing_ok=True)
        print("[INFO] Sin actualizaciones pendientes de sistema o plugins. Finalizando sin reporte.")
        sys.exit(0)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest_payload = {
        "generated_at_utc": timestamp,
        "jenkins_url": jenkins_url,
        "instructions": (
            "Las actualizaciones detectadas son candidatas, no aprobaciones. "
            "Para aprobar Core, cambie approved_core_update a true. "
            "Agregue unicamente los nombres autorizados a approved_os_packages "
            "y approved_plugins. Sin cambios explicitos, no se aplicara nada."
        ),
        "available_core_update": sys_updates["core"],
        "available_os_packages": sys_updates["os_packages"],
        "available_plugins": plugin_updates,
        "approved_core_update": False,
        "approved_os_packages": [],
        "approved_plugins": [],
    }

    manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    # Construcción del reporte detallado
    lines = [
        f"REPORTE DE ACTUALIZACIONES PENDIENTES DE JENKINS ({timestamp})",
        "=" * 70,
        f"Instancia: {jenkins_url}",
        f"Manifiesto generado en: {manifest_path}",
        "",
        "ACCIÓN REQUERIDA ANTES DE LAS 12:30:",
        f"Edite '{manifest_path}' para aprobar explicitamente solo las actualizaciones elegidas.",
        "Cambie approved_core_update a true para Core y agregue nombres a approved_os_packages o approved_plugins.",
        "Las listas aprobadas quedan vacias por defecto; si no se editan, la ejecucion de las 12:30 abortara.",
        "",
        "1. JENKINS CORE:",
        f"   - {sys_updates['core']['package']} -> {sys_updates['core']['target_version']}" if has_core else "   - Sin cambios pendientes",
        "",
        f"2. PAQUETES DEL SISTEMA OPERATIVO ({len(sys_updates['os_packages'])}):",
    ]

    if has_os:
        for pkg in sys_updates["os_packages"]:
            lines.append(f"   - {pkg['package']} ({pkg['target_version']})")
    else:
        lines.append("   - Sin cambios pendientes")

    lines.append("")
    lines.append(f"3. PLUGINS DE JENKINS ({len(plugin_updates)}):")
    if has_plugins:
        for plg in plugin_updates:
            lines.append(f"   - {plg['name']} (actual: {plg['current_version']}) - {plg['display_name']}")
    else:
        lines.append("   - Sin cambios pendientes")

    report_text = "\n".join(lines)
    subject = f"[SRE Action Required] Actualizaciones disponibles en Jenkins ({len(plugin_updates)} plugins, Core: {'Sí' if has_core else 'No'})"

    send_email_report(subject, report_text)
    print(f"[OK] Reporte enviado y manifiesto guardado en {manifest_path}")


if __name__ == "__main__":
    main()