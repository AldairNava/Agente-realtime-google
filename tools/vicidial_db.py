import logging

logger = logging.getLogger(__name__)

class VicidialDatabase:
    """Mockup de consultas tipo SQL hacia el servidor DB de Asterisk/CRM"""
    def __init__(self):
        # Registros ficticios en memoria
        self.clientes = {
            "5512345678": {"nombre": "Juan Pérez González", "deuda": "$500 MXN vencida", "estatus": "Alta / Activo", "paquete": "Internet Simétrico Plus"},
            "8199887766": {"nombre": "María López Torres", "deuda": "$0 MXN (Al Corriente)", "estatus": "Cuenta Suspendida a petición del usuario", "paquete": "Telefonía Básica"},
            "5584268222": {"nombre": "Erik Garcia Cuevas", "deuda": "$0 MXN (Al Corriente)", "estatus": "Alta / Activo", "paquete": "Platinum Card - Preaprobado", "limite_preaprobado": "$85,000 MXN", "buro": "Sin observaciones", "antiguedad_crediticia": "4 años"}
        }

    def consultar_cliente_por_telefono(self, telefono: str) -> str:
        """
        Busca el perfil de un cliente (su deuda y sus servicios activos) a partir de su número de teléfono. 
        Pídele verbalmente al usuario sus 10 dígitos y mételos aquí para confirmarlo en sistema.
        Parámetros obligatorios:
          - telefono (str): El número sin ningún espacio ni guiones, ej. '5512345678'.
        """
        logger.info(f"[Asterisk SQL] Lanzando consulta paralela por el ANI/Número: {telefono}")
        # Limpieza sencilla
        telefono = str(telefono).replace(" ", "").replace("-", "")
        
        if telefono in self.clientes:
            c = self.clientes[telefono]
            info = f"Registro CRM encontrado -> Nombre: {c['nombre']}, Estatus: {c['estatus']}, Deuda: {c['deuda']}"
            if c.get('paquete'):
                info += f", Producto: {c['paquete']}"
            if c.get('limite_preaprobado'):
                info += f", Límite Preaprobado: {c['limite_preaprobado']}"
            if c.get('buro'):
                info += f", Buró: {c['buro']}"
            if c.get('antiguedad_crediticia'):
                info += f", Antigüedad Crediticia: {c['antiguedad_crediticia']}"
            return info + "."
            
        return f"No pude extraer datos. El número telefónico {telefono} no aparece en la base de datos de Vicidial asignado a ninguna cuenta."
