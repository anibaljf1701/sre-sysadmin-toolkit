#!/usr/bin/env python3
"""
Jenkins Patch Applier & Automated Rollback (EC2 / Systemd environments)
Validates human-approved manifest, creates an AWS EBS snapshot before patching,
applies OS/Core/Plugin updates, runs a 3-condition healthcheck (180s timeout),
and executes disk-level rollback if Jenkins fails to recover.
Uses 100% Python Standard Library + AWS CLI / Instance Profile.
"""

import argparse
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
import time
import urllib.error
import urllib.request


def get_env(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(key, default)
    if required and not val:
        print(f"[ERROR] Variable de entorno requerida no definida: {key}", file=sys.stderr)
        sys.exit(1)
    return val or ""


def send_alert_email(subject: str, body: str) -> None:
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


def validate_manifest(manifest_path: Path) -> dict:
    """Aborta si el archivo no existe, está vacío o no contiene aprobaciones."""
    if not manifest_path.exists() or not manifest_path.is_file():
        print(f"[ABORT] Manifiesto no encontrado en '{manifest_path}'. Nada que ejecutar.")
        sys.exit(0)

    if manifest_path.stat().st_size == 0:
        print(f"[ABORT] Manifiesto '{manifest_path}' está vacío. Nada que ejecutar.")
        sys.exit(0)

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[ABORT] Manifiesto inválido (JSON corrupto): {exc}", file=sys.stderr)
        sys.exit(1)

    has_core = bool(data.get("approved_core_update"))
    has_os = len(data.get("approved_os_packages") or []) > 0
    has_plugins = len(data.get("approved_plugins") or []) > 0

    if not (has_core or has_os or has_plugins):
        print("[ABORT] El manifiesto no contiene paquetes ni plugins aprobados. Abortando ejecución.")
        sys.exit(0)

    return data


def get_ec2_metadata() -> dict:
    """Obtiene Instance ID, Region y Availability Zone usando IMDSv2."""
    token_req = urllib.request.Request(
        "http://169.254.169.254/latest/api/token",
        method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
    )
    with urllib.request.urlopen(token_req, timeout=5) as resp:
        token = resp.read().decode("utf-8")

    headers = {"X-aws-ec2-metadata-token": token}

    def fetch(path: str) -> str:
        req = urllib.request.Request(f"http://169.254.169.254/latest/meta-data/{path}", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.read().decode("utf-8")

    return {
        "instance_id": fetch("instance-id"),
        "region": fetch("placement/region"),
        "az": fetch("placement/availability-zone"),
    }


def create_ebs_snapshot(ec2_meta: dict, device_name: str, is_dedicated_vol: bool) -> dict:
    """Crea snapshots del volumen root y del volumen donde reside JENKINS_HOME."""
    region = ec2_meta["region"]
    instance_id = ec2_meta["instance_id"]

    desc_cmd = [
        "aws", "ec2", "describe-instances",
        "--region", region,
        "--instance-ids", instance_id,
        "--query", "Reservations[0].Instances[0]",
        "--output", "json",
    ]
    instance = json.loads(subprocess.run(desc_cmd, capture_output=True, text=True, check=True).stdout)
    root_device = instance["RootDeviceName"]
    block_devices = {
        mapping["DeviceName"]: mapping.get("Ebs", {}).get("VolumeId")
        for mapping in instance["BlockDeviceMappings"]
    }
    root_volume_id = block_devices.get(root_device)
    jenkins_volume_id = block_devices.get(device_name)

    if not root_volume_id:
        raise RuntimeError(f"No se encontró el volumen EBS root asociado a {root_device} en {instance_id}")
    if not jenkins_volume_id:
        raise RuntimeError(f"No se encontró volumen EBS asociado al dispositivo {device_name} en {instance_id}")

    jenkins_is_root = jenkins_volume_id == root_volume_id
    if jenkins_is_root == is_dedicated_vol:
        raise RuntimeError(
            f"IS_DEDICATED_DATA_VOLUME={str(is_dedicated_vol).lower()} no coincide con el volumen "
            f"configurado para JENKINS_HOME ({device_name})"
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    def snapshot_volume(volume_id: str, purpose: str) -> dict:
        snap_cmd = [
            "aws", "ec2", "create-snapshot",
            "--region", region,
            "--volume-id", volume_id,
            "--description", f"Pre-patch Jenkins {purpose} backup {instance_id} ({ts})",
            "--tag-specifications",
            f"ResourceType=snapshot,Tags=[{{Key=Name,Value=jenkins-prepatch-{purpose}-{ts}}},{{Key=ManagedBy,Value=jenkins-patch-applier}}]",
            "--query", "SnapshotId",
            "--output", "text",
        ]
        snapshot_id = subprocess.run(snap_cmd, capture_output=True, text=True, check=True).stdout.strip()
        print(f"[INFO] Esperando snapshot {snapshot_id} ({purpose}, volumen: {volume_id})...")
        subprocess.run(
            ["aws", "ec2", "wait", "snapshot-completed", "--region", region, "--snapshot-ids", snapshot_id],
            check=True,
        )
        print(f"[OK] Snapshot {snapshot_id} completado.")
        return {"volume_id": volume_id, "snapshot_id": snapshot_id}

    root_info = snapshot_volume(root_volume_id, "root")
    jenkins_info = root_info if jenkins_is_root else snapshot_volume(jenkins_volume_id, "jenkins-home")
    return {"root": root_info, "jenkins": jenkins_info}


def set_quiet_down(base_url: str, user: str, token: str, enable: bool) -> None:
    endpoint = "quietDown" if enable else "cancelQuietDown"
    url = f"{base_url.rstrip('/')}/{endpoint}"
    auth_str = base64.b64encode(f"{user}:{token}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(url, method="POST", headers={"Authorization": f"Basic {auth_str}"})
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as exc:
        print(f"[WARN] No se pudo cambiar estado {endpoint}: {exc}")


def apply_updates(approved: dict, base_url: str, user: str, token: str, cli_jar: str, service_name: str) -> None:
    set_quiet_down(base_url, user, token, enable=True)

    # 1. Paquetes de Sistema y Jenkins Core
    packages_to_upgrade = list(approved.get("approved_os_packages") or [])
    if approved.get("approved_core_update"):
        packages_to_upgrade.append("jenkins")

    if packages_to_upgrade:
        print(f"[INFO] Actualizando paquetes del sistema/core: {', '.join(packages_to_upgrade)}")
        if shutil.which("apt-get"):
            env = os.environ.copy()
            env["DEBIAN_FRONTEND"] = "noninteractive"
            subprocess.run(
                ["apt-get", "install", "-y", "--only-upgrade", *packages_to_upgrade],
                env=env,
                check=True,
            )
        elif shutil.which("dnf") or shutil.which("yum"):
            pkg_mgr = "dnf" if shutil.which("dnf") else "yum"
            subprocess.run([pkg_mgr, "update", "-y", *packages_to_upgrade], check=True)

    # 2. Plugins de Jenkins vía CLI
    plugins = approved.get("approved_plugins") or []
    if plugins:
        print(f"[INFO] Actualizando plugins de Jenkins: {', '.join(plugins)}")
        subprocess.run(
            [
                "java", "-jar", cli_jar,
                "-s", base_url,
                "-auth", f"{user}:{token}",
                "install-plugin", *plugins,
            ],
            check=True,
        )

    # 3. Reinicio limpio del servicio
    print(f"[INFO] Reiniciando servicio '{service_name}'...")
    subprocess.run(["systemctl", "restart", service_name], check=True)


def run_healthcheck(base_url: str, user: str, token: str, service_name: str, patch_start_iso: str, timeout_sec: int = 180) -> tuple[bool, str]:
    """
    Valida 3 condiciones dentro de una ventana de 180 segundos:
    1. HTTP 200 en /login
    2. API /api/json responde JSON válido con quietingDown == False
    3. Sin errores fatales de carga de plugins en journalctl
    """
    deadline = time.time() + timeout_sec
    auth_str = base64.b64encode(f"{user}:{token}".encode("utf-8")).decode("ascii")
    last_error = "Timeout esperando respuesta de Jenkins"

    while time.time() < deadline:
        try:
            # Condición 1: HTTP 200 en /login
            login_req = urllib.request.Request(f"{base_url.rstrip('/')}/login")
            with urllib.request.urlopen(login_req, timeout=10) as login_resp:
                if login_resp.status != 200:
                    last_error = f"/login devolvió HTTP {login_resp.status}"
                    time.sleep(10)
                    continue

            # Condición 2: API /api/json válida y quietingDown == False
            api_req = urllib.request.Request(
                f"{base_url.rstrip('/')}/api/json",
                headers={"Authorization": f"Basic {auth_str}"},
            )
            with urllib.request.urlopen(api_req, timeout=10) as api_resp:
                payload = json.loads(api_resp.read().decode("utf-8"))
                if payload.get("quietingDown") is not False:
                    if payload.get("quietingDown") is True:
                        set_quiet_down(base_url, user, token, enable=False)
                        last_error = "Jenkins sigue en modo quietingDown"
                    else:
                        last_error = "La API no confirmó quietingDown=false"
                    time.sleep(10)
                    continue

            # Condición 3: Ausencia de errores fatales de plugins en logs del servicio
            journal_res = subprocess.run(
                ["journalctl", "-u", service_name, "--since", patch_start_iso, "--no-pager"],
                capture_output=True,
                text=True,
                check=False,
            )
            if journal_res.returncode != 0:
                return False, (
                    f"journalctl falló con código {journal_res.returncode}: "
                    f"{journal_res.stderr.strip()}"
                )

            fatal_markers = ("Failed Loading plugin", "HudsonFailedToLoad", "SEVERE: Error injecting")
            for marker in fatal_markers:
                if marker in journal_res.stdout:
                    return False, f"Error fatal detectado en logs de Jenkins: '{marker}'"

            return True, "Todas las verificaciones de salud superadas (HTTP 200, API activa, 0 errores fatales)."

        except Exception as exc:
            last_error = str(exc)
            time.sleep(10)

    return False, f"Healthcheck falló tras {timeout_sec}s. Último error: {last_error}"


def execute_rollback(ec2_meta: dict, ebs_info: dict, device_name: str, jenkins_home: str, service_name: str, is_dedicated_vol: bool) -> str:
    """
    Restaura JENKINS_HOME si está dedicado y solicita a EC2 reemplazar el volumen root.
    """
    region = ec2_meta["region"]
    instance_id = ec2_meta["instance_id"]
    jenkins_info = ebs_info["jenkins"]
    root_info = ebs_info["root"]

    subprocess.run(["systemctl", "stop", service_name], check=False)

    data_rollback = "JENKINS_HOME comparte el volumen root; se restaurará junto con el sistema."
    if is_dedicated_vol:
        old_vol = jenkins_info["volume_id"]
        data_snapshot_id = jenkins_info["snapshot_id"]
        subprocess.run(["umount", "-l", jenkins_home], check=True)
        subprocess.run(
            ["aws", "ec2", "detach-volume", "--region", region, "--volume-id", old_vol],
            check=True,
        )
        subprocess.run(
            ["aws", "ec2", "wait", "volume-available", "--region", region, "--volume-ids", old_vol],
            check=True,
        )

        new_vol_res = subprocess.run(
            [
                "aws", "ec2", "create-volume",
                "--region", region,
                "--availability-zone", ec2_meta["az"],
                "--snapshot-id", data_snapshot_id,
                "--volume-type", "gp3",
                "--query", "VolumeId",
                "--output", "text",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        new_vol_id = new_vol_res.stdout.strip()
        subprocess.run(
            ["aws", "ec2", "wait", "volume-available", "--region", region, "--volume-ids", new_vol_id],
            check=True,
        )
        subprocess.run(
            [
                "aws", "ec2", "attach-volume",
                "--region", region,
                "--volume-id", new_vol_id,
                "--instance-id", instance_id,
                "--device", device_name,
            ],
            check=True,
        )
        subprocess.run(
            ["aws", "ec2", "wait", "volume-in-use", "--region", region, "--volume-ids", new_vol_id],
            check=True,
        )
        subprocess.run(["mount", device_name, jenkins_home], check=True)
        data_rollback = (
            f"JENKINS_HOME restaurado desde {data_snapshot_id} en el volumen {new_vol_id}; "
            "Jenkins permanecerá detenido durante el reemplazo del root."
        )

    root_task_res = subprocess.run(
        [
            "aws", "ec2", "create-replace-root-volume-task",
            "--region", region,
            "--instance-id", instance_id,
            "--snapshot-id", root_info["snapshot_id"],
            "--no-delete-replaced-root-volume",
            "--query", "ReplaceRootVolumeTask.ReplaceRootVolumeTaskId",
            "--output", "text",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    root_task_id = root_task_res.stdout.strip()
    return (
        "ROLLBACK DEL VOLUMEN ROOT SOLICITADO A EC2. La instancia se reiniciará automáticamente; "
        "el volumen root reemplazado se conserva para recuperación manual.\n"
        f"- Snapshot root: {root_info['snapshot_id']}\n"
        f"- Tarea de reemplazo: {root_task_id}\n"
        f"- {data_rollback}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aplica actualizaciones aprobadas de Jenkins sobre EC2 con EBS Snapshot y Rollback automático."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Ruta obligatoria al archivo JSON de actualizaciones aprobadas.",
    )
    args = parser.parse_args()

    # 1. Validación estricta antes de tocar la instancia o AWS
    approved_data = validate_manifest(args.manifest)

    jenkins_url = get_env("JENKINS_URL", "http://localhost:8080")
    jenkins_user = get_env("JENKINS_USER", required=True)
    jenkins_token = get_env("JENKINS_API_TOKEN", required=True)
    cli_jar = get_env("JENKINS_CLI_JAR", "/var/cache/jenkins/war/WEB-INF/lib/cli-2.462.jar")
    service_name = get_env("JENKINS_SERVICE_NAME", "jenkins")
    jenkins_home = get_env("JENKINS_HOME", "/var/lib/jenkins")
    device_name = get_env("JENKINS_EBS_DEVICE", "/dev/xvdf")
    is_dedicated = get_env("IS_DEDICATED_DATA_VOLUME", "true").lower() == "true"

    ec2_meta = get_ec2_metadata()
    ebs_info = create_ebs_snapshot(ec2_meta, device_name, is_dedicated)

    patch_start_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        apply_updates(approved_data, jenkins_url, jenkins_user, jenkins_token, cli_jar, service_name)
    except Exception as exc:
        rollback_msg = execute_rollback(ec2_meta, ebs_info, device_name, jenkins_home, service_name, is_dedicated)
        send_alert_email(
            subject="[CRITICAL] Fallo durante parcheo de Jenkins - Rollback solicitado",
            body=f"Error aplicando actualizaciones: {exc}\n\n{rollback_msg}",
        )
        sys.exit(1)

    # 2. Healthcheck post-parcheo (ventana máxima de 3 minutos)
    healthy, details = run_healthcheck(jenkins_url, jenkins_user, jenkins_token, service_name, patch_start_iso, timeout_sec=180)

    if healthy:
        # Limpiamos el manifiesto para evitar reprocesamiento al día siguiente
        args.manifest.unlink(missing_ok=True)
        send_alert_email(
            subject="[OK] Ventana de parcheo Jenkins completada exitosamente",
            body=(
                f"Las actualizaciones aprobadas fueron aplicadas y verificadas.\n"
                f"Snapshots preventivos generados: root={ebs_info['root']['snapshot_id']}, "
                f"JENKINS_HOME={ebs_info['jenkins']['snapshot_id']}\n"
                f"Resultado Healthcheck: {details}"
            ),
        )
        print(f"[OK] {details}")
    else:
        rollback_msg = execute_rollback(ec2_meta, ebs_info, device_name, jenkins_home, service_name, is_dedicated)
        send_alert_email(
            subject="[CRITICAL] Healthcheck de Jenkins fallido - Rollback solicitado",
            body=f"Motivo del fallo: {details}\n\n{rollback_msg}",
        )
        print(f"[CRITICAL] {details}\n{rollback_msg}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()