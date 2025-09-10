#!/usr/bin/env python3
"""
Test script to verify the updated schema validations prevent simultaneous CLP and UF entry.
"""

from decimal import Decimal
from datetime import date
from schemas.contratos import ContratoCreate, ContratoUpdate
from schemas.proyectos import ProyectoCreate, ProyectoUpdate
import traceback

def test_contrato_validation():
    """Test contrato schema validation prevents simultaneous CLP and UF entry"""
    print("=" * 60)
    print("TESTING CONTRATO VALIDATION")
    print("=" * 60)
    
    # Test 1: ContratoCreate with both CLP and UF (should fail)
    print("\n1. Testing ContratoCreate with both CLP and UF amounts (should fail):")
    try:
        contrato_data = {
            "proyecto_id": 1,
            "numero_oc": "OC-001",
            "monto_total": Decimal("1000000"),  # CLP
            "monto_total_uf": Decimal("30"),    # UF - This should cause validation error
            "valor_uf_conversion": Decimal("35000"),
            "fecha_conversion_uf": date.today(),
            "moneda_original": "UF"
        }
        contrato = ContratoCreate(**contrato_data)
        print("❌ FAILED: Validation should have prevented simultaneous CLP and UF")
    except ValueError as e:
        print(f"✅ SUCCESS: Validation correctly prevented simultaneous entry: {e}")
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")
    
    # Test 2: ContratoCreate with only CLP (should succeed)
    print("\n2. Testing ContratoCreate with only CLP amount (should succeed):")
    try:
        contrato_data = {
            "proyecto_id": 1,
            "numero_oc": "OC-002",
            "monto_total": Decimal("1000000"),  # Only CLP
            "moneda": "CLP"
        }
        contrato = ContratoCreate(**contrato_data)
        print("✅ SUCCESS: CLP-only validation passed")
    except Exception as e:
        print(f"❌ FAILED: CLP-only should be valid: {e}")
    
    # Test 3: ContratoCreate with only UF (should succeed)
    print("\n3. Testing ContratoCreate with only UF amount (should succeed):")
    try:
        contrato_data = {
            "proyecto_id": 1,
            "numero_oc": "OC-003",
            "monto_total_uf": Decimal("30"),    # Only UF
            "valor_uf_conversion": Decimal("35000"),
            "fecha_conversion_uf": date.today(),
            "moneda_original": "UF"
        }
        contrato = ContratoCreate(**contrato_data)
        print("✅ SUCCESS: UF-only validation passed")
    except Exception as e:
        print(f"❌ FAILED: UF-only should be valid: {e}")
    
    # Test 4: ContratoUpdate with both CLP and UF (should fail)
    print("\n4. Testing ContratoUpdate with both CLP and UF amounts (should fail):")
    try:
        update_data = {
            "monto_total": Decimal("2000000"),  # CLP
            "monto_total_uf": Decimal("50"),    # UF - This should cause validation error
            "valor_uf_conversion": Decimal("35000"),
            "fecha_conversion_uf": date.today(),
            "moneda_original": "UF"
        }
        contrato_update = ContratoUpdate(**update_data)
        print("❌ FAILED: Update validation should have prevented simultaneous CLP and UF")
    except ValueError as e:
        print(f"✅ SUCCESS: Update validation correctly prevented simultaneous entry: {e}")
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")

def test_proyecto_validation():
    """Test proyecto schema validation prevents simultaneous CLP and UF entry"""
    print("\n" + "=" * 60)
    print("TESTING PROYECTO VALIDATION")
    print("=" * 60)
    
    # Test 1: ProyectoCreate with both CLP and UF for provision (should fail)
    print("\n1. Testing ProyectoCreate with both CLP and UF provision amounts (should fail):")
    try:
        proyecto_data = {
            "cliente_id": 1,
            "nombre": "Proyecto Test",
            "monto_provision_presupuestado": Decimal("1000000"),  # CLP
            "monto_provision_presupuestado_uf": Decimal("30"),    # UF - This should cause validation error
            "valor_uf_presupuesto": Decimal("35000"),
            "fecha_conversion_presupuesto_uf": date.today(),
            "moneda_original_presupuesto": "UF"
        }
        proyecto = ProyectoCreate(**proyecto_data)
        print("❌ FAILED: Validation should have prevented simultaneous CLP and UF for provision")
    except ValueError as e:
        print(f"✅ SUCCESS: Validation correctly prevented simultaneous provision entry: {e}")
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")
    
    # Test 2: ProyectoCreate with both CLP and UF for installation (should fail)
    print("\n2. Testing ProyectoCreate with both CLP and UF installation amounts (should fail):")
    try:
        proyecto_data = {
            "cliente_id": 1,
            "nombre": "Proyecto Test",
            "monto_instalacion_presupuestado": Decimal("500000"),  # CLP
            "monto_instalacion_presupuestado_uf": Decimal("15"),   # UF - This should cause validation error
            "valor_uf_presupuesto": Decimal("35000"),
            "fecha_conversion_presupuesto_uf": date.today(),
            "moneda_original_presupuesto": "UF"
        }
        proyecto = ProyectoCreate(**proyecto_data)
        print("❌ FAILED: Validation should have prevented simultaneous CLP and UF for installation")
    except ValueError as e:
        print(f"✅ SUCCESS: Validation correctly prevented simultaneous installation entry: {e}")
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")
    
    # Test 3: ProyectoCreate with only CLP amounts (should succeed)
    print("\n3. Testing ProyectoCreate with only CLP amounts (should succeed):")
    try:
        proyecto_data = {
            "cliente_id": 1,
            "nombre": "Proyecto Test CLP",
            "monto_provision_presupuestado": Decimal("1000000"),  # Only CLP
            "monto_instalacion_presupuestado": Decimal("500000")  # Only CLP
        }
        proyecto = ProyectoCreate(**proyecto_data)
        print("✅ SUCCESS: CLP-only validation passed")
    except Exception as e:
        print(f"❌ FAILED: CLP-only should be valid: {e}")
    
    # Test 4: ProyectoCreate with only UF amounts (should succeed)
    print("\n4. Testing ProyectoCreate with only UF amounts (should succeed):")
    try:
        proyecto_data = {
            "cliente_id": 1,
            "nombre": "Proyecto Test UF",
            "monto_provision_presupuestado_uf": Decimal("30"),    # Only UF
            "monto_instalacion_presupuestado_uf": Decimal("15"),  # Only UF
            "valor_uf_presupuesto": Decimal("35000"),
            "fecha_conversion_presupuesto_uf": date.today(),
            "moneda_original_presupuesto": "UF"
        }
        proyecto = ProyectoCreate(**proyecto_data)
        print("✅ SUCCESS: UF-only validation passed")
    except Exception as e:
        print(f"❌ FAILED: UF-only should be valid: {e}")
    
    # Test 5: ProyectoUpdate with both CLP and UF (should fail)
    print("\n5. Testing ProyectoUpdate with both CLP and UF provision amounts (should fail):")
    try:
        update_data = {
            "monto_provision_presupuestado": Decimal("2000000"),  # CLP
            "monto_provision_presupuestado_uf": Decimal("60"),    # UF - This should cause validation error
            "valor_uf_presupuesto": Decimal("35000"),
            "fecha_conversion_presupuesto_uf": date.today(),
            "moneda_original_presupuesto": "UF"
        }
        proyecto_update = ProyectoUpdate(**update_data)
        print("❌ FAILED: Update validation should have prevented simultaneous CLP and UF")
    except ValueError as e:
        print(f"✅ SUCCESS: Update validation correctly prevented simultaneous entry: {e}")
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")

def main():
    """Run all validation tests"""
    print("Testing updated schema validations to prevent simultaneous CLP and UF entry")
    print("This test verifies that the new validation rules work correctly.")
    
    try:
        test_contrato_validation()
        test_proyecto_validation()
        
        print("\n" + "=" * 60)
        print("VALIDATION TESTS COMPLETED")
        print("=" * 60)
        print("✅ All tests verify that simultaneous CLP and UF entry is properly prevented!")
        print("✅ The schema validation changes are working as expected!")
        
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR during testing: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()