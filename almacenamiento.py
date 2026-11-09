"""Persona 2: SQLite autoritativo para lotes y extensión; exportación unidireccional."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3

from config import ruta_proyecto
from contratos import huella, validar_decision, validar_estrategia
from personas import generar_personas


def _ahora():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class Almacen:
    """Cada escritura es transaccional; las versiones nunca se sobrescriben.

    La detección de duplicados compara los quince valores de perfil (sin ID o
    nombre), mediante un índice SHA256, a lo sumo una consulta por nueva persona.
    ``duplicate_attributes`` cuenta perfiles ya vistos, incluso dentro del lote.
    No elimina ni modifica duplicados. Tamaño máximo explícito: 10 000 personas.
    """

    def __init__(self, ruta="datos/teamforge.sqlite3"):
        self.ruta = ruta_proyecto(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self._conexion() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS lotes (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT UNIQUE,
                    n INTEGER NOT NULL,
                    semilla INTEGER NOT NULL,
                    duplicate_attributes INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS personas (
                    id TEXT PRIMARY KEY,
                    lote_id TEXT NOT NULL REFERENCES lotes(id),
                    fingerprint TEXT NOT NULL,
                    data TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_personas_fingerprint ON personas(fingerprint);
                CREATE INDEX IF NOT EXISTS idx_personas_lote ON personas(lote_id);
                CREATE TABLE IF NOT EXISTS experimentos (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidencias (
                    experimento_id TEXT NOT NULL REFERENCES experimentos(id) ON DELETE CASCADE,
                    id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(experimento_id, id)
                );
                CREATE TABLE IF NOT EXISTS versiones (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS versiones_experimento (
                    experimento_id TEXT NOT NULL REFERENCES experimentos(id) ON DELETE CASCADE,
                    version_id TEXT NOT NULL REFERENCES versiones(id),
                    PRIMARY KEY(experimento_id, version_id)
                );
                CREATE TABLE IF NOT EXISTS activas (
                    experimento_id TEXT PRIMARY KEY REFERENCES experimentos(id) ON DELETE CASCADE,
                    version_id TEXT NOT NULL REFERENCES versiones(id),
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisiones (
                    experimento_id TEXT NOT NULL REFERENCES experimentos(id) ON DELETE CASCADE,
                    id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(experimento_id, id)
                );
            """)

    @contextmanager
    def _conexion(self):
        db = sqlite3.connect(self.ruta, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def registrar_lote(self, n, semilla):
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 10_000:
            raise ValueError("El lote debe contener entre 1 y 10000 personas.")
        if isinstance(semilla, bool) or not isinstance(semilla, int):
            raise ValueError("La semilla del lote debe ser un entero.")
        personas = generar_personas(n=n, semilla=semilla)
        created_at = _ahora()
        with self._conexion() as db:
            cursor = db.execute(
                "INSERT INTO lotes(n,semilla,created_at) VALUES (?,?,?)",
                (n, semilla, created_at),
            )
            lote_id = f"lote-{cursor.lastrowid:06d}"
            db.execute("UPDATE lotes SET id=? WHERE seq=?", (lote_id, cursor.lastrowid))
            duplicates = 0
            for persona in personas:
                persona["id"] = f"{lote_id}:{persona['id']}"
                fingerprint = huella({k: persona[k] for k in ("declarado", "real", "estimado")})
                duplicates += bool(db.execute(
                    "SELECT 1 FROM personas WHERE fingerprint=? LIMIT 1", (fingerprint,)
                ).fetchone())
                db.execute("INSERT INTO personas VALUES (?,?,?,?)", (
                    persona["id"], lote_id, fingerprint, _json(persona),
                ))
            db.execute("UPDATE lotes SET duplicate_attributes=? WHERE id=?", (duplicates, lote_id))
        return {"id": lote_id, "n": n, "semilla": semilla,
                "duplicate_attributes": duplicates, "created_at": created_at,
                "personas": personas}

    def listar_lotes(self):
        with self._conexion() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,n,semilla,duplicate_attributes,created_at FROM lotes ORDER BY seq"
            )]

    def personas_lote(self, lote_id):
        with self._conexion() as db:
            if not db.execute("SELECT 1 FROM lotes WHERE id=?", (lote_id,)).fetchone():
                raise ValueError(f"Lote inexistente: {lote_id}")
            return [json.loads(row[0]) for row in db.execute(
                "SELECT data FROM personas WHERE lote_id=? ORDER BY id", (lote_id,)
            )]

    def guardar_experimento(self, experimento_id, datos):
        if not isinstance(experimento_id, str) or not experimento_id:
            raise ValueError("El experimento requiere un identificador no vacío.")
        if not isinstance(datos, dict):
            raise ValueError("El experimento debe ser un objeto JSON.")
        now = _ahora()
        with self._conexion() as db:
            prior = db.execute("SELECT created_at FROM experimentos WHERE id=?", (experimento_id,)).fetchone()
            record = dict(datos)
            record["experiment_id"] = experimento_id
            record["created_at"] = prior[0] if prior else datos.get("created_at", now)
            record["updated_at"] = now
            db.execute("""INSERT INTO experimentos VALUES (?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at""",
                (experimento_id, _json(record), record["created_at"], now))

    def cargar_experimento(self, experimento_id):
        with self._conexion() as db:
            row = db.execute("SELECT data FROM experimentos WHERE id=?", (experimento_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def _guardar_registro(self, table, experimento_id, record, db):
        # table solo proviene de constantes internas, nunca de entradas del usuario.
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
            raise ValueError("El registro requiere un identificador no vacío.")
        data = _json(record)
        prior = db.execute(
            f"SELECT data FROM {table} WHERE experimento_id=? AND id=?", (experimento_id, record["id"])
        ).fetchone()
        if prior:
            if prior[0] != data:
                raise ValueError(f"Registro inmutable: {record['id']}")
            return
        db.execute(f"INSERT INTO {table} VALUES (?,?,?,?)",
                   (experimento_id, record["id"], data, _ahora()))

    def guardar_evidencia(self, experimento_id, evidencia):
        with self._conexion() as db:
            self._guardar_registro("evidencias", experimento_id, evidencia, db)

    def listar_evidencias(self, experimento_id):
        with self._conexion() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT data FROM evidencias WHERE experimento_id=? ORDER BY rowid", (experimento_id,)
            )]

    def guardar_version(self, estrategia):
        validar_estrategia(estrategia)
        data = _json(estrategia)
        with self._conexion() as db:
            prior = db.execute("SELECT data FROM versiones WHERE id=?", (estrategia["id"],)).fetchone()
            if prior:
                if prior[0] != data:
                    raise ValueError(f"La versión {estrategia['id']} es inmutable.")
                return
            db.execute("INSERT INTO versiones VALUES (?,?,?)", (estrategia["id"], data, _ahora()))

    def listar_versiones(self):
        with self._conexion() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM versiones ORDER BY rowid")]

    def activar_version(self, experimento_id, version_id):
        with self._conexion() as db:
            db.execute("INSERT OR IGNORE INTO versiones_experimento VALUES (?,?)", (experimento_id, version_id))
            db.execute("""INSERT INTO activas VALUES (?,?,?) ON CONFLICT(experimento_id)
                DO UPDATE SET version_id=excluded.version_id,updated_at=excluded.updated_at""",
                (experimento_id, version_id, _ahora()))

    def version_activa(self, experimento_id):
        with self._conexion() as db:
            row = db.execute("""SELECT v.data FROM versiones v JOIN activas a ON v.id=a.version_id
                WHERE a.experimento_id=?""", (experimento_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def guardar_decision(self, experimento_id, decision):
        validar_decision(decision)
        with self._conexion() as db:
            self._guardar_registro("decisiones", experimento_id, decision, db)
            for key in ("parent_id", "candidate_id"):
                version_id = decision.get(key)
                if version_id and db.execute("SELECT 1 FROM versiones WHERE id=?", (version_id,)).fetchone():
                    db.execute("INSERT OR IGNORE INTO versiones_experimento VALUES (?,?)", (experimento_id, version_id))

    def listar_decisiones(self, experimento_id):
        with self._conexion() as db:
            return [json.loads(row[0]) for row in db.execute(
                "SELECT data FROM decisiones WHERE experimento_id=? ORDER BY rowid", (experimento_id,)
            )]

    def reiniciar_experimento(self, experimento_id):
        """Borra solo este experimento y sus vínculos; conserva lotes y versiones."""
        with self._conexion() as db:
            db.execute("DELETE FROM experimentos WHERE id=?", (experimento_id,))

    def exportar_experimento(self, experimento_id, ruta="resultados/evolucion.json"):
        with self._conexion() as db:
            # Una transacción de lectura evita mezclar snapshots de escrituras concurrentes.
            db.execute("BEGIN")
            row = db.execute("SELECT data FROM experimentos WHERE id=?", (experimento_id,)).fetchone()
            if row is None:
                raise ValueError(f"Experimento inexistente: {experimento_id}")
            data = json.loads(row[0])
            data["schema_version"] = 1
            data["decisions"] = [json.loads(r[0]) for r in db.execute(
                "SELECT data FROM decisiones WHERE experimento_id=? ORDER BY rowid", (experimento_id,))]
            data["evidence"] = [json.loads(r[0]) for r in db.execute(
                "SELECT data FROM evidencias WHERE experimento_id=? ORDER BY rowid", (experimento_id,))]
            data["versions"] = [json.loads(r[0]) for r in db.execute("""
                SELECT v.data FROM versiones v JOIN versiones_experimento ve ON v.id=ve.version_id
                WHERE ve.experimento_id=? ORDER BY v.rowid""", (experimento_id,))]
            active = db.execute("""SELECT v.data FROM versiones v JOIN activas a ON v.id=a.version_id
                WHERE a.experimento_id=?""", (experimento_id,)).fetchone()
            data["active_version"] = json.loads(active[0]) if active else None
        target = ruta_proyecto(ruta)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(target)
