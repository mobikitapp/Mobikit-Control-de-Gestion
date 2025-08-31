#!/usr/bin/env python3
"""
Script para inicializar las categorías y subcategorías de muebles
"""
from app import app, db
from models import CategoriaMuebleModel, SubcategoriaMuebleModel, CategoriaMueble, SubcategoriaCocina, SubcategoriaCloset

def init_categorias():
    """Inicializa las categorías y subcategorías de muebles"""
    print("Inicializando categorías de muebles...")
    
    # Crear categorías principales
    categorias_data = [
        {'nombre': CategoriaMueble.COCINA, 'descripcion': 'Muebles de cocina'},
        {'nombre': CategoriaMueble.CLOSET, 'descripcion': 'Muebles de closet/vestidor'},
        {'nombre': CategoriaMueble.BANO, 'descripcion': 'Muebles de baño'}
    ]
    
    categorias_creadas = {}
    
    for cat_data in categorias_data:
        categoria = CategoriaMuebleModel.query.filter_by(nombre=cat_data['nombre']).first()
        if not categoria:
            categoria = CategoriaMuebleModel(
                nombre=cat_data['nombre'],
                descripcion=cat_data['descripcion']
            )
            db.session.add(categoria)
            print(f"Creada categoría: {cat_data['nombre'].value}")
        else:
            print(f"Categoría ya existe: {cat_data['nombre'].value}")
        
        categorias_creadas[cat_data['nombre']] = categoria
    
    db.session.commit()
    
    # Crear subcategorías para cocina
    subcategorias_cocina = [
        {'nombre': SubcategoriaCocina.BASES, 'descripcion': 'Muebles base de cocina'},
        {'nombre': SubcategoriaCocina.MURALES, 'descripcion': 'Muebles murales de cocina'},
        {'nombre': SubcategoriaCocina.KITS, 'descripcion': 'Kits de cocina'},
        {'nombre': SubcategoriaCocina.CUBIERTAS, 'descripcion': 'Cubiertas de cocina'}
    ]
    
    categoria_cocina = categorias_creadas[CategoriaMueble.COCINA]
    
    for subcat_data in subcategorias_cocina:
        subcategoria = SubcategoriaMuebleModel.query.filter_by(
            categoria_id=categoria_cocina.id,
            nombre_cocina=subcat_data['nombre']
        ).first()
        
        if not subcategoria:
            subcategoria = SubcategoriaMuebleModel(
                categoria_id=categoria_cocina.id,
                nombre_cocina=subcat_data['nombre'],
                descripcion=subcat_data['descripcion']
            )
            db.session.add(subcategoria)
            print(f"Creada subcategoría de cocina: {subcat_data['nombre'].value}")
        else:
            print(f"Subcategoría de cocina ya existe: {subcat_data['nombre'].value}")
    
    # Crear subcategorías para closet
    subcategorias_closet = [
        {'nombre': SubcategoriaCloset.INTERIORES, 'descripcion': 'Interiores de closet'},
        {'nombre': SubcategoriaCloset.PIERNAS, 'descripcion': 'Piernas de closet'},
        {'nombre': SubcategoriaCloset.PUERTAS, 'descripcion': 'Puertas de closet'}
    ]
    
    categoria_closet = categorias_creadas[CategoriaMueble.CLOSET]
    
    for subcat_data in subcategorias_closet:
        subcategoria = SubcategoriaMuebleModel.query.filter_by(
            categoria_id=categoria_closet.id,
            nombre_closet=subcat_data['nombre']
        ).first()
        
        if not subcategoria:
            subcategoria = SubcategoriaMuebleModel(
                categoria_id=categoria_closet.id,
                nombre_closet=subcat_data['nombre'],
                descripcion=subcat_data['descripcion']
            )
            db.session.add(subcategoria)
            print(f"Creada subcategoría de closet: {subcat_data['nombre'].value}")
        else:
            print(f"Subcategoría de closet ya existe: {subcat_data['nombre'].value}")
    
    db.session.commit()
    print("✓ Inicialización de categorías completada")

if __name__ == "__main__":
    with app.app_context():
        init_categorias()