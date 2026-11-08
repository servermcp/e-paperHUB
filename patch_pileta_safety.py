from pathlib import Path

tuya_file = Path('/root/epaper-hub/integrations/tuya_client.py')
code = tuya_file.read_text(encoding='utf-8')

target = '        return {"ok": True, "devices_total": len(devs), "pina_on": pina_on, "sgo_on": sgo_on}'
replacement = '''        # Si no hay ningun dispositivo asignado a la pileta, asegurar que quede en estado Apagada / Inactiva
        has_pileta_assigned = any(grp == "pileta_filtro" for grp in assignments.values())
        if not has_pileta_assigned:
            with database.db_session() as conn:
                conn.execute(
                    "UPDATE device_state_cache SET status_text = 'Apagada', is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE device_id = 'pileta_filtro'"
                )

        return {"ok": True, "devices_total": len(devs), "pina_on": pina_on, "sgo_on": sgo_on}'''

if target in code and 'has_pileta_assigned' not in code:
    code = code.replace(target, replacement)
    tuya_file.write_text(code, encoding='utf-8')
    print("tuya_client.py patched with pileta safety fallback!")
else:
    print("Already patched or target not found.")
