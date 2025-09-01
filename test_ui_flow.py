
#!/usr/bin/env python3
"""
Script para probar funcionalidades de UI y flujos de frontend
"""

import os
import sys
import requests
import time
from urllib.parse import urljoin

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class UIFlowTester:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.errors = []
        self.warnings = []
        
    def log_error(self, test: str, error: str):
        error_msg = f"❌ UI ERROR en {test}: {error}"
        self.errors.append(error_msg)
        print(error_msg)
        
    def log_warning(self, test: str, warning: str):
        warning_msg = f"⚠️  UI WARNING en {test}: {warning}"
        self.warnings.append(warning_msg)
        print(warning_msg)
        
    def log_success(self, test: str, message: str):
        success_msg = f"✅ UI {test}: {message}"
        print(success_msg)
        
    def test_home_page(self):
        """Test main dashboard access"""
        try:
            response = self.session.get(self.base_url)
            if response.status_code == 200:
                if "Mobikit" in response.text or "dashboard" in response.text.lower():
                    self.log_success("HOME", "Página principal carga correctamente")
                else:
                    self.log_warning("HOME", "Página carga pero contenido inesperado")
            else:
                self.log_error("HOME", f"Status code: {response.status_code}")
        except Exception as e:
            self.log_error("HOME", f"Error de conexión: {str(e)}")
            
    def test_navigation_pages(self):
        """Test main navigation pages"""
        pages = [
            ("/clientes", "Clientes"),
            ("/proyectos", "Proyectos"), 
            ("/contratos", "Contratos"),
            ("/fabricacion", "Órdenes de Fabricación"),
            ("/despachos", "Despachos"),
            ("/calendario", "Calendario"),
            ("/areas", "Áreas"),
            ("/comercial", "Comercial")
        ]
        
        for url, name in pages:
            try:
                response = self.session.get(urljoin(self.base_url, url))
                if response.status_code == 200:
                    self.log_success("NAVEGACION", f"Página {name} accesible")
                elif response.status_code == 302:
                    self.log_warning("NAVEGACION", f"Página {name} redirige (posible auth)")
                else:
                    self.log_error("NAVEGACION", f"Página {name} error {response.status_code}")
            except Exception as e:
                self.log_error("NAVEGACION", f"Error accediendo {name}: {str(e)}")
                
    def test_form_pages(self):
        """Test form pages accessibility"""
        form_pages = [
            ("/clientes/nuevo", "Nuevo Cliente"),
            ("/proyectos/nuevo", "Nuevo Proyecto"),
            ("/contratos/nuevo", "Nuevo Contrato"),
            ("/fabricacion/nueva", "Nueva OF"),
            ("/despachos/nuevo", "Nuevo Despacho")
        ]
        
        for url, name in form_pages:
            try:
                response = self.session.get(urljoin(self.base_url, url))
                if response.status_code == 200:
                    # Check if form elements exist
                    if "form" in response.text.lower() and "submit" in response.text.lower():
                        self.log_success("FORMULARIOS", f"Formulario {name} carga correctamente")
                    else:
                        self.log_warning("FORMULARIOS", f"Formulario {name} posiblemente incompleto")
                elif response.status_code == 302:
                    self.log_warning("FORMULARIOS", f"Formulario {name} redirige")
                else:
                    self.log_error("FORMULARIOS", f"Formulario {name} error {response.status_code}")
            except Exception as e:
                self.log_error("FORMULARIOS", f"Error accediendo formulario {name}: {str(e)}")
                
    def test_static_resources(self):
        """Test static resources loading"""
        static_resources = [
            "/static/css/style.css",
            "/static/css/custom.css", 
            "/static/js/app.js",
            "/static/img/mobikit-logo.png"
        ]
        
        for resource in static_resources:
            try:
                response = self.session.get(urljoin(self.base_url, resource))
                if response.status_code == 200:
                    self.log_success("RECURSOS", f"Recurso {resource} carga OK")
                else:
                    self.log_error("RECURSOS", f"Recurso {resource} no encontrado ({response.status_code})")
            except Exception as e:
                self.log_error("RECURSOS", f"Error cargando {resource}: {str(e)}")
                
    def test_api_endpoints(self):
        """Test API endpoints that might be used by frontend"""
        api_endpoints = [
            ("/api/clientes", "GET"),
            ("/api/proyectos", "GET"),
            ("/api/areas", "GET")
        ]
        
        for endpoint, method in api_endpoints:
            try:
                if method == "GET":
                    response = self.session.get(urljoin(self.base_url, endpoint))
                else:
                    continue  # Skip non-GET for safety
                    
                if response.status_code == 200:
                    try:
                        data = response.json()
                        self.log_success("API", f"Endpoint {endpoint} responde JSON")
                    except:
                        self.log_warning("API", f"Endpoint {endpoint} responde pero no JSON")
                elif response.status_code in [401, 403]:
                    self.log_warning("API", f"Endpoint {endpoint} requiere autenticación")
                else:
                    self.log_error("API", f"Endpoint {endpoint} error {response.status_code}")
            except Exception as e:
                self.log_error("API", f"Error en endpoint {endpoint}: {str(e)}")
                
    def test_javascript_functionality(self):
        """Test if JavaScript is working by checking for common errors"""
        try:
            response = self.session.get(self.base_url)
            if response.status_code == 200:
                # Check for common JavaScript patterns
                js_patterns = [
                    "document.addEventListener",
                    "function",
                    "$(document).ready",  # jQuery
                    "fetch(",
                    "axios"
                ]
                
                found_js = any(pattern in response.text for pattern in js_patterns)
                if found_js:
                    self.log_success("JAVASCRIPT", "JavaScript presente en las páginas")
                else:
                    self.log_warning("JAVASCRIPT", "No se detectó JavaScript en las páginas")
                    
        except Exception as e:
            self.log_error("JAVASCRIPT", f"Error verificando JavaScript: {str(e)}")
            
    def run_ui_tests(self):
        """Run all UI tests"""
        print("🖥️  Iniciando pruebas de UI - Mobikit")
        print("=" * 60)
        
        self.test_home_page()
        self.test_navigation_pages()
        self.test_form_pages()
        self.test_static_resources()
        self.test_api_endpoints()
        self.test_javascript_functionality()
        
        # Report results
        print("\n" + "=" * 60)
        print("📊 REPORTE DE PRUEBAS UI")
        print("=" * 60)
        
        if not self.errors and not self.warnings:
            print("🎉 ¡ÉXITO! Todas las pruebas de UI pasaron.")
        else:
            if self.errors:
                print(f"❌ Se detectaron {len(self.errors)} ERRORES de UI:")
                for error in self.errors:
                    print(f"   {error}")
                    
            if self.warnings:
                print(f"⚠️  Se detectaron {len(self.warnings)} ADVERTENCIAS de UI:")
                for warning in self.warnings:
                    print(f"   {warning}")
                    
        return len(self.errors) == 0

if __name__ == "__main__":
    # Check if server is running
    try:
        response = requests.get("http://localhost:5000", timeout=5)
        print("✅ Servidor detectado en puerto 5000")
    except:
        print("❌ No se puede conectar al servidor en puerto 5000")
        print("   Asegúrate de que la aplicación esté ejecutándose")
        exit(1)
        
    tester = UIFlowTester()
    success = tester.run_ui_tests()
    
    if success:
        print("\n✅ Pruebas de UI completadas exitosamente")
        exit(0)
    else:
        print("\n❌ Pruebas de UI completadas con errores")
        exit(1)
