import os
import shutil
from pathlib import Path

def migrate_assets():
    base_dir = Path(__file__).parent.absolute()
    assets_dir = base_dir / "assets"
    old_recordings = base_dir / "recordings"

    campaigns = ["amex", "retencion", "ventas_izzi", "plata"]

    # 1. Crear estructura base
    for camp in campaigns:
        camp_dir = assets_dir / camp
        (camp_dir / "llamadas_grabadas").mkdir(parents=True, exist_ok=True)
        (camp_dir / "audios_pregrabados").mkdir(parents=True, exist_ok=True)
        (camp_dir / "rag_docs").mkdir(parents=True, exist_ok=True)

    # 2. Mover de la raíz recordings/pregrabados_*
    if old_recordings.exists():
        for camp in campaigns:
            src = old_recordings / f"pregrabados_{camp}"
            dest = assets_dir / camp / "audios_pregrabados"
            if src.exists() and src.is_dir():
                for item in src.iterdir():
                    shutil.move(str(item), str(dest / item.name))
                print(f"[OK] Movidos pregrabados de {camp} desde recordings/ a assets/")

    # 3. Mover de assets/*/recordings a assets/*/audios_pregrabados (si existe)
    for camp in campaigns:
        old_assets_rec = assets_dir / camp / "recordings"
        dest = assets_dir / camp / "audios_pregrabados"
        if old_assets_rec.exists() and old_assets_rec.is_dir():
            for item in old_assets_rec.iterdir():
                if item.is_file():
                    shutil.move(str(item), str(dest / item.name))
            shutil.rmtree(old_assets_rec)
            print(f"[OK] Renombrado assets/{camp}/recordings a audios_pregrabados")

    # 4. Eliminar vieja carpeta recordings/
    if old_recordings.exists():
        shutil.rmtree(old_recordings)
        print(f"[OK] Carpeta raíz 'recordings' eliminada por completo.")

if __name__ == "__main__":
    migrate_assets()
