
#!/usr/bin/env python3
"""
Script to remove all calendar events from the database
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import EventoEntrega

def remove_all_calendar_events():
    """Remove all calendar events from the database"""
    try:
        with app.app_context():
            # Count existing events
            total_events = db.session.query(EventoEntrega).count()
            print(f"Found {total_events} calendar events to remove...")
            
            if total_events == 0:
                print("No calendar events found in the database.")
                return
            
            # Delete all events
            deleted_count = db.session.query(EventoEntrega).delete()
            db.session.commit()
            
            print(f"Successfully removed {deleted_count} calendar events from the database.")
            
    except Exception as e:
        print(f"Error removing calendar events: {str(e)}")
        db.session.rollback()
        return False
    
    return True

if __name__ == "__main__":
    print("=" * 50)
    print("REMOVING ALL CALENDAR EVENTS")
    print("=" * 50)
    
    confirm = input("Are you sure you want to remove ALL calendar events? This action cannot be undone. (yes/no): ")
    
    if confirm.lower() == 'yes':
        success = remove_all_calendar_events()
        if success:
            print("\n✓ Calendar events removal completed successfully!")
        else:
            print("\n✗ Failed to remove calendar events.")
    else:
        print("Operation cancelled.")
