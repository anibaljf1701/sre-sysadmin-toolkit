#!/usr/bin/env python3
"""
Test script para verificar la sintaxis de los scripts Python.
AWS Best Practices: Testing básico sin dependencias externas.
"""

import os
import sys
import importlib.util
import subprocess
from pathlib import Path

def print_header(text):
    """Imprime un encabezado formateado."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def print_success(text):
    """Imprime mensaje de éxito."""
    print(f"✅ {text}")

def print_warning(text):
    """Imprime mensaje de advertencia."""
    print(f"⚠️  {text}")

def print_error(text):
    """Imprime mensaje de error."""
    print(f"❌ {text}")

def test_python_syntax(file_path):
    """Testea la sintaxis de un archivo Python."""
    try:
        # Intentar compilar el archivo
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        compile(source, file_path, 'exec')
        return True, None
    except SyntaxError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Error inesperado: {str(e)}"

def test_import(file_path):
    """Testea si el archivo puede ser importado."""
    try:
        module_name = Path(file_path).stem
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return True, None
    except Exception as e:
        return False, str(e)

def check_aws_imports(file_path):
    """Verifica que las importaciones de AWS estén disponibles."""
    required_imports = ['boto3', 'logging', 'json', 'os', 'datetime']
    missing_imports = []
    
    for import_name in required_imports:
        try:
            __import__(import_name)
        except ImportError:
            missing_imports.append(import_name)
    
    if missing_imports:
        return False, f"Importaciones faltantes: {', '.join(missing_imports)}"
    return True, None

def check_lambda_handler(file_path):
    """Verifica que el archivo tenga una función lambda_handler."""
    try:
        spec = importlib.util.spec_from_file_location("test_module", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, 'lambda_handler'):
            handler = getattr(module, 'lambda_handler')
            if callable(handler):
                return True, None
            else:
                return False, "lambda_handler no es callable"
        else:
            return False, "No se encontró lambda_handler"
    except Exception as e:
        return False, f"Error verificando lambda_handler: {str(e)}"

def analyze_file(file_path):
    """Analiza un archivo Python individual."""
    print(f"\n📁 Analizando: {file_path}")
    
    # Test 1: Sintaxis básica
    success, error = test_python_syntax(file_path)
    if not success:
        print_error(f"Error de sintaxis: {error}")
        return False
    
    print_success("Sintaxis válida")
    
    # Test 2: Importaciones AWS
    success, error = check_aws_imports(file_path)
    if not success:
        print_warning(error)
    else:
        print_success("Importaciones AWS disponibles")
    
    # Test 3: Importación del módulo
    success, error = test_import(file_path)
    if not success:
        print_error(f"Error importando módulo: {error}")
        return False
    
    print_success("Módulo importable")
    
    # Test 4: Lambda handler (solo para scripts Lambda)
    if 'scheduler' in str(file_path) or 'register' in str(file_path):
        success, error = check_lambda_handler(file_path)
        if not success:
            print_error(error)
            return False
        print_success("lambda_handler encontrado y válido")
    
    return True

def check_bash_script():
    """Verifica el script bash básico."""
    bash_script = Path("bash_scripts/log_rotation_s3.sh")
    
    print(f"\n📁 Analizando: {bash_script}")
    
    if not bash_script.exists():
        print_error("Script bash no encontrado")
        return False
    
    # Verificar que sea ejecutable
    if not os.access(bash_script, os.X_OK):
        print_warning("Script bash no es ejecutable")
        print("  Ejecuta: chmod +x bash_scripts/log_rotation_s3.sh")
    
    # Verificar shebang
    with open(bash_script, 'r') as f:
        first_line = f.readline().strip()
    
    if first_line != "#!/bin/bash":
        print_warning(f"Shebang inesperado: {first_line}")
    else:
        print_success("Shebang correcto")
    
    # Verificar que tenga la función main
    with open(bash_script, 'r') as f:
        content = f.read()
    
    if "main()" in content:
        print_success("Función main encontrada")
    else:
        print_warning("No se encontró función main")
    
    return True

def run_flake8_check():
    """Ejecuta flake8 para verificar estilo (si está instalado)."""
    try:
        print("\n🔍 Ejecutando verificación de estilo (flake8)...")
        
        # Buscar todos los scripts Python
        python_files = []
        for root, dirs, files in os.walk("python_scripts"):
            for file in files:
                if file.endswith(".py"):
                    python_files.append(os.path.join(root, file))
        
        if not python_files:
            print_warning("No se encontraron archivos Python para analizar")
            return True
        
        # Ejecutar flake8
        result = subprocess.run(
            ["flake8"] + python_files,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print_success("Estilo de código OK (flake8)")
        else:
            print_warning("Problemas de estilo encontrados:")
            print(result.stdout)
            if result.stderr:
                print(f"Errores: {result.stderr}")
            
            # Instrucciones para instalar flake8
            print("\n💡 Para instalar flake8:")
            print("  pip install flake8")
        
        return result.returncode == 0
        
    except FileNotFoundError:
        print_warning("flake8 no instalado, omitiendo verificación de estilo")
        print("  Instala con: pip install flake8")
        return True

def main():
    """Función principal de testing."""
    print_header("🧪 SRE SysAdmin Toolkit - Test de Calidad")
    print("Verificando scripts Python y Bash con AWS Best Practices...")
    
    # Cambiar al directorio del proyecto
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    print(f"\n📂 Directorio de trabajo: {project_root}")
    
    all_tests_passed = True
    
    # Testear scripts bash
    if not check_bash_script():
        all_tests_passed = False
    
    # Encontrar y testear todos los scripts Python
    python_files = []
    for root, dirs, files in os.walk("python_scripts"):
        for file in files:
            if file.endswith(".py"):
                python_files.append(Path(root) / file)
    
    if not python_files:
        print_error("No se encontraron scripts Python en python_scripts/")
        all_tests_passed = False
    else:
        print(f"\n🔍 Encontrados {len(python_files)} scripts Python:")
        for file in python_files:
            print(f"  • {file}")
        
        # Analizar cada archivo
        for python_file in python_files:
            if not analyze_file(python_file):
                all_tests_passed = False
    
    # Verificación de estilo (opcional)
    run_flake8_check()
    
    # Resumen
    print_header("📊 Resumen de Tests")
    
    if all_tests_passed:
        print_success("✅ Todos los tests básicos pasaron!")
        print("\n🎉 Los scripts están listos para su uso.")
        print("📚 Revisa README.md para instrucciones de despliegue en AWS.")
    else:
        print_error("❌ Algunos tests fallaron")
        print("\n🔧 Corrección necesaria antes del despliegue:")
        print("  1. Revisa los errores arriba")
        print("  2. Corrige problemas de sintaxis")
        print("  3. Asegura que lambda_handler exista en scripts Lambda")
        print("  4. Ejecuta este test nuevamente")
    
    # Próximos pasos
    print_header("🚀 Próximos Pasos")
    print("""
1. Configura el entorno:
   ./setup.sh

2. Prueba los scripts localmente:
   source .env
   ./bash_scripts/log_rotation_s3.sh --help

3. Despliega en AWS:
   - Sigue las instrucciones en README.md
   - Usa AWS SAM o AWS CLI

4. Configura monitoreo:
   - CloudWatch Metrics
   - CloudWatch Logs
   - Alertas por errores

5. Etiqueta instancias EC2:
   aws ec2 create-tags --resources i-... --tags Key=Environment,Value=Dev
    """)
    
    sys.exit(0 if all_tests_passed else 1)

if __name__ == "__main__":
    main()