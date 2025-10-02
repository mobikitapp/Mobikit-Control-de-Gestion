
from app import app, db
from models import Proyecto, TareaComercial, EstadoComercial
from services.comercial_service import ComercialService
from datetime import date, timedelta

def check_maestra_project():
    """Revisar el proyecto Maestra y crear tarea si es necesario"""
    with app.app_context():
        try:
            # Buscar proyecto Maestra
            proyecto_maestra = (db.session.query(Proyecto)
                              .filter(Proyecto.nombre.ilike('%maestra%'))
                              .filter_by(activo=True)
                              .first())
            
            if not proyecto_maestra:
                print("❌ No se encontró el proyecto 'Maestra'")
                return
            
            print(f"✅ Proyecto encontrado: {proyecto_maestra.nombre}")
            print(f"   - ID: {proyecto_maestra.id}")
            print(f"   - Cliente: {proyecto_maestra.cliente.nombre if proyecto_maestra.cliente else 'Sin cliente'}")
            print(f"   - Estado: {proyecto_maestra.estado_comercial.value if proyecto_maestra.estado_comercial else 'Sin estado'}")
            print(f"   - Vendedor ID: {proyecto_maestra.vendedor_id}")
            
            if proyecto_maestra.vendedor_user:
                print(f"   - Vendedor: {proyecto_maestra.vendedor_user.nombre_completo}")
            else:
                print("   - ⚠️  Sin vendedor asignado")
            
            # Verificar si tiene tareas pendientes
            tareas_pendientes = (db.session.query(TareaComercial)
                               .filter_by(proyecto_id=proyecto_maestra.id, completada=False)
                               .filter(TareaComercial.titulo.ilike('%presupuesto%'))
                               .all())
            
            print(f"   - Tareas de presupuesto pendientes: {len(tareas_pendientes)}")
            
            for tarea in tareas_pendientes:
                print(f"     * {tarea.titulo}")
                print(f"       Vendedor: {tarea.vendedor.nombre_completo if tarea.vendedor else 'Sin vendedor'}")
                print(f"       Fecha límite: {tarea.fecha_limite}")
            
            # Si está pendiente de presupuesto pero no tiene tareas, crear una
            if (proyecto_maestra.estado_comercial == EstadoComercial.PENDIENTE_PRESUPUESTO and 
                proyecto_maestra.vendedor_id and 
                not tareas_pendientes):
                
                print("\n🔧 Creando tarea automática para presupuesto...")
                
                # Crear tarea
                titulo = f"Crear presupuesto para proyecto: {proyecto_maestra.nombre}"
                descripcion = f"""Proyecto pendiente de presupuesto que requiere atención urgente.

Cliente: {proyecto_maestra.cliente.nombre if proyecto_maestra.cliente else 'Sin cliente'}
Proyecto: {proyecto_maestra.nombre}

Tareas a realizar:
• Completar montos netos de venta (provisión e instalación)
• Definir márgenes de ganancia
• Establecer fecha de presupuesto
• Actualizar estado del proyecto a PRESUPUESTADO

Los montos deben ser precios finales al cliente, no costos internos.

⚠️ IMPORTANTE: Este proyecto está pendiente de presupuesto y requiere atención inmediata.

Nota: Tarea creada automáticamente por script de corrección."""

                # Fecha límite urgente (2 días hábiles)
                fecha_limite = date.today() + timedelta(days=2)
                while fecha_limite.weekday() >= 5:  # Evitar fines de semana
                    fecha_limite += timedelta(days=1)

                tarea = TareaComercial()
                tarea.proyecto_id = proyecto_maestra.id
                tarea.vendedor_id = proyecto_maestra.vendedor_id
                tarea.titulo = titulo
                tarea.descripcion = descripcion
                tarea.fecha_limite = fecha_limite
                tarea.created_by = proyecto_maestra.vendedor_id  # Asignar al vendedor
                tarea.completada = False
                
                db.session.add(tarea)
                db.session.commit()
                
                print("✅ Tarea creada exitosamente")
                print(f"   - Título: {titulo}")
                print(f"   - Fecha límite: {fecha_limite}")
                print(f"   - Asignada a: {proyecto_maestra.vendedor_user.nombre_completo}")
                
            elif not proyecto_maestra.vendedor_id:
                print("\n⚠️  El proyecto no tiene vendedor asignado. Asigna un vendedor primero.")
                
            elif proyecto_maestra.estado_comercial != EstadoComercial.PENDIENTE_PRESUPUESTO:
                print(f"\n ℹ️  El proyecto no está en estado PENDIENTE_PRESUPUESTO (está en {proyecto_maestra.estado_comercial.value})")
                
            else:
                print("\n✅ El proyecto ya tiene tareas de presupuesto asignadas")
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    check_maestra_project()
