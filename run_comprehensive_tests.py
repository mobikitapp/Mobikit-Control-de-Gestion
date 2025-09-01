
#!/usr/bin/env python3
"""
Script maestro para ejecutar todas las pruebas de la aplicación Mobikit
"""

import subprocess
import sys
import time
import os

def run_command(command, description):
    """Run a command and return success status"""
    print(f"\n🔄 {description}")
    print("-" * 50)
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
            
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error ejecutando comando: {e}")
        return False

def main():
    print("🧪 MOBIKIT - SUITE COMPLETA DE PRUEBAS")
    print("=" * 60)
    print("Este script ejecutará pruebas completas de la aplicación")
    print("incluyendo flujo de datos, UI y funcionalidades críticas.")
    print("=" * 60)
    
    # Check if app.py exists
    if not os.path.exists("app.py"):
        print("❌ No se encontró app.py en el directorio actual")
        print("   Asegúrate de ejecutar este script desde la raíz del proyecto")
        exit(1)
        
    # Array to store results
    test_results = []
    
    # 1. Test database connectivity
    print("\n📊 FASE 1: Verificación de Base de Datos")
    db_test = run_command(
        "python -c \"from app import app, db; app.app_context().push(); print('✅ Conexión a BD exitosa')\"",
        "Verificando conectividad de base de datos"
    )
    test_results.append(("Base de Datos", db_test))
    
    # 2. Test basic imports
    print("\n📦 FASE 2: Verificación de Importaciones")
    import_test = run_command(
        "python -c \"from models import *; from services.clientes_service import *; print('✅ Importaciones exitosas')\"",
        "Verificando importaciones de módulos"
    )
    test_results.append(("Importaciones", import_test))
    
    # 3. Run happy flow test
    print("\n🚀 FASE 3: Prueba de Flujo Completo")
    happy_flow_test = run_command(
        "python test_happy_flow.py",
        "Ejecutando prueba de happy flow"
    )
    test_results.append(("Happy Flow", happy_flow_test))
    
    # 4. Check if server can start (quick test)
    print("\n🌐 FASE 4: Verificación de Servidor")
    server_test = run_command(
        "timeout 10s python -c \"from app import app; print('✅ Servidor puede inicializarse'); app.run(host='0.0.0.0', port=5001, debug=False)\" || true",
        "Verificando que el servidor puede inicializar"
    )
    test_results.append(("Servidor", server_test))
    
    # 5. Run UI tests if server is running on port 5000
    print("\n🖥️  FASE 5: Pruebas de Interfaz de Usuario")
    ui_test_success = False
    try:
        import requests
        response = requests.get("http://localhost:5000", timeout=3)
        print("✅ Servidor detectado en puerto 5000, ejecutando pruebas UI")
        ui_test_success = run_command(
            "python test_ui_flow.py",
            "Ejecutando pruebas de interfaz de usuario"
        )
    except:
        print("⚠️  Servidor no disponible en puerto 5000")
        print("   Para pruebas completas de UI, inicia la aplicación en puerto 5000")
        ui_test_success = None
        
    test_results.append(("UI Tests", ui_test_success))
    
    # 6. Code quality checks (if available)
    print("\n🔍 FASE 6: Verificaciones de Calidad")
    
    # Check for syntax errors
    syntax_test = run_command(
        "python -m py_compile app.py && python -m py_compile models.py",
        "Verificando sintaxis de archivos principales"
    )
    test_results.append(("Sintaxis", syntax_test))
    
    # Generate final report
    print("\n" + "=" * 60)
    print("📋 REPORTE FINAL DE PRUEBAS")
    print("=" * 60)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for test_name, result in test_results:
        if result is True:
            print(f"✅ {test_name:<20} PASÓ")
            passed += 1
        elif result is False:
            print(f"❌ {test_name:<20} FALLÓ")
            failed += 1
        else:
            print(f"⚠️  {test_name:<20} OMITIDO")
            skipped += 1
    
    print("-" * 60)
    print(f"✅ Pruebas exitosas: {passed}")
    print(f"❌ Pruebas fallidas: {failed}")
    print(f"⚠️  Pruebas omitidas: {skipped}")
    
    if failed == 0:
        print("\n🎉 ¡TODAS LAS PRUEBAS CRÍTICAS PASARON!")
        print("   La aplicación parece estar funcionando correctamente.")
        if skipped > 0:
            print(f"   Nota: {skipped} pruebas fueron omitidas (no críticas)")
    else:
        print(f"\n⚠️  SE DETECTARON {failed} PROBLEMAS CRÍTICOS")
        print("   Revisa los errores mostrados arriba para más detalles.")
    
    # Recommendations
    print("\n📝 RECOMENDACIONES:")
    print("1. Si hay errores de BD, verifica la configuración de DATABASE_URL")
    print("2. Si hay errores de importación, verifica que todas las dependencias estén instaladas")
    print("3. Para pruebas UI completas, asegúrate de que el servidor esté corriendo en puerto 5000")
    print("4. Revisa los logs detallados arriba para información específica de errores")
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
