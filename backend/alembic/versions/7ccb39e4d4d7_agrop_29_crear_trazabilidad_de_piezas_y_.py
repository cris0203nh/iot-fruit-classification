
"""AGROP-29: esquema de trazabilidad AgroScan.

Revision ID: 7ccb39e4d4d7
Revises:
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "7ccb39e4d4d7"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def create_empty_schema() -> None:
    """Crear el esquema completo cuando SQLite está vacío."""

    # LOTES
    op.create_table(
        "lots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("product", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("responsible", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lots_code", "lots", ["code"], unique=True)

    # MEDICIONES DE PESO
    op.create_table(
        "measurements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("boot_id", sa.String(64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("weight_g", sa.Float(), nullable=False),
        sa.Column("stable", sa.Boolean(), nullable=False),
        sa.Column("calibration_version", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("zero_confirmed", sa.Boolean(), nullable=False),
        sa.UniqueConstraint(
            "device_id", "boot_id", "seq",
            name="uq_measurement_seq",
        ),
    )
    op.create_index(
        "ix_measurements_device_id",
        "measurements",
        ["device_id"],
    )

    # PIEZAS
    op.create_table(
        "pieces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["lot_id"], ["lots.id"],
            name="fk_pieces_lot_id_lots",
        ),
        sa.UniqueConstraint(
            "lot_id", "code",
            name="uq_piece_lot_code",
        ),
    )
    op.create_index("ix_pieces_lot_id", "pieces", ["lot_id"])

    # EVALUACIONES
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("piece_id", sa.String(64), nullable=False),
        sa.Column("piece_ref_id", sa.Integer(), nullable=True),
        sa.Column("product", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("weight_grams", sa.Float(), nullable=True),
        sa.Column("image_count", sa.Integer(), nullable=False),
        sa.Column("visual_category", sa.String(50), nullable=True),
        sa.Column("review_note", sa.String(500), nullable=True),
        sa.Column("calibration_reference", sa.String(100), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("rules_version", sa.String(50), nullable=True),
        sa.Column("weight_pre_g", sa.Float(), nullable=True),
        sa.Column("weight_pre_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weight_post_g", sa.Float(), nullable=True),
        sa.Column("weight_post_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weight_pre_measurement_id", sa.Integer(), nullable=True),
        sa.Column("weight_post_measurement_id", sa.Integer(), nullable=True),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("boot_id", sa.String(64), nullable=True),
        sa.Column("failure_reason", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["lot_id"], ["lots.id"],
            name="fk_evaluations_lot_id_lots",
        ),
        sa.ForeignKeyConstraint(
            ["piece_ref_id"], ["pieces.id"],
            name="fk_evaluations_piece_ref_id_pieces",
        ),
        sa.ForeignKeyConstraint(
            ["weight_pre_measurement_id"], ["measurements.id"],
            name="fk_evaluations_weight_pre_measurement_id_measurements",
        ),
        sa.ForeignKeyConstraint(
            ["weight_post_measurement_id"], ["measurements.id"],
            name="fk_evaluations_weight_post_measurement_id_measurements",
        ),
    )
    op.create_index("ix_evaluations_lot_id", "evaluations", ["lot_id"])
    op.create_index("ix_evaluations_piece_id", "evaluations", ["piece_id"])
    op.create_index(
        "ix_evaluations_piece_ref_id",
        "evaluations",
        ["piece_ref_id"],
    )

    # IMÁGENES
    op.create_table(
        "images",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("evaluation_id", sa.Integer(), nullable=False),
        sa.Column("view", sa.String(30), nullable=False),
        sa.Column("relative_path", sa.String(300), nullable=False),
        sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["evaluations.id"],
            name="fk_images_evaluation_id_evaluations",
        ),
    )
    op.create_index(
        "ix_images_evaluation_id",
        "images",
        ["evaluation_id"],
    )

    # REVISIONES
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("evaluation_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("previous_value", sa.String(50), nullable=True),
        sa.Column("updated_value", sa.String(50), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluation_id"], ["evaluations.id"],
            name="fk_reviews_evaluation_id_evaluations",
        ),
    )
    op.create_index(
        "ix_reviews_evaluation_id",
        "reviews",
        ["evaluation_id"],
    )


def upgrade() -> None:
    connection = op.get_bind()
    inspector = inspect(connection)

    existing_tables = set(inspector.get_table_names())

    # CASO 1: base de datos completamente vacía.
    if "lots" not in existing_tables:
        create_empty_schema()
        return
    # CASO 2: base existente. Agregar únicamente trazabilidad.
    if "pieces" not in existing_tables:
        op.create_table(
            "pieces",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("lot_id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(64), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["lot_id"], ["lots.id"],
                name="fk_pieces_lot_id_lots",
            ),
            sa.UniqueConstraint(
                "lot_id", "code",
                name="uq_piece_lot_code",
            ),
        )

    # Crear índice de piezas si todavía no existe.
    inspector = inspect(connection)
    piece_indexes = {
        index["name"] for index in inspector.get_indexes("pieces")
    }

    if "ix_pieces_lot_id" not in piece_indexes:
        op.create_index(
            "ix_pieces_lot_id",
            "pieces",
            ["lot_id"],
        )

    # Obtener las columnas actuales de evaluations.
    inspector = inspect(connection)

    columns = {
        column["name"]
        for column in inspector.get_columns("evaluations")
    }

    # Identificar las claves foráneas existentes.
    existing_fks = inspector.get_foreign_keys("evaluations")

    fk_signatures = {
        (
            tuple(fk["constrained_columns"]),
            fk["referred_table"],
            tuple(fk["referred_columns"]),
        )
        for fk in existing_fks
    }

    # Preparar las nuevas relaciones.
    relationships = [
        (
            "piece_ref_id",
            "pieces",
            "fk_evaluations_piece_ref_id_pieces",
        ),
        (
            "weight_pre_measurement_id",
            "measurements",
            "fk_evaluations_weight_pre_measurement_id_measurements",
        ),
        (
            "weight_post_measurement_id",
            "measurements",
            "fk_evaluations_weight_post_measurement_id_measurements",
        ),
    ]

    # Reconstruir evaluations mediante el mecanismo compatible
    # con SQLite, conservando las columnas y registros existentes.
    with op.batch_alter_table(
        "evaluations",
        recreate="always",
    ) as batch_op:

        for column_name, referred_table, constraint_name in relationships:

            if column_name not in columns:
                batch_op.add_column(
                    sa.Column(column_name, sa.Integer(), nullable=True)
                )

            signature = (
                (column_name,),
                referred_table,
                ("id",),
            )

            if signature not in fk_signatures:
                batch_op.create_foreign_key(
                    constraint_name,
                    referred_table,
                    [column_name],
                    ["id"],
                )

    # Crear el índice de piece_ref_id si falta.
    inspector = inspect(connection)

    evaluation_indexes = {
        index["name"]
        for index in inspector.get_indexes("evaluations")
    }

    if "ix_evaluations_piece_ref_id" not in evaluation_indexes:
        op.create_index(
            "ix_evaluations_piece_ref_id",
            "evaluations",
            ["piece_ref_id"],
        )

    # Vincular las evaluaciones existentes con sus piezas.
    evaluations = connection.execute(
        sa.text("""
            SELECT id, lot_id, piece_id, created_at
            FROM evaluations
            ORDER BY id
        """)
    ).mappings().all()

    for evaluation in evaluations:
        piece = connection.execute(
            sa.text("""
                SELECT id
                FROM pieces
                WHERE lot_id = :lot_id AND code = :code
            """),
            {
                "lot_id": evaluation["lot_id"],
                "code": evaluation["piece_id"],
            },
        ).first()

        if piece is None:
            result = connection.execute(
                sa.text("""
                    INSERT INTO pieces
                    (lot_id, code, status, created_at)
                    VALUES (:lot_id, :code, :status, :created_at)
                """),
                {
                    "lot_id": evaluation["lot_id"],
                    "code": evaluation["piece_id"],
                    "status": "registered",
                    "created_at": evaluation["created_at"],
                },
            )
            piece_id = result.lastrowid
        else:
            piece_id = piece[0]

        connection.execute(
            sa.text("""
                UPDATE evaluations
                SET piece_ref_id = :piece_ref_id
                WHERE id = :evaluation_id
            """),
            {
                "piece_ref_id": piece_id,
                "evaluation_id": evaluation["id"],
            },
        )
def downgrade() -> None:
    """Retirar las nuevas relaciones de trazabilidad."""

    connection = op.get_bind()
    tables = set(inspect(connection).get_table_names())

    if "evaluations" not in tables:
        return

    columns = {
        column["name"]
        for column in inspect(connection).get_columns("evaluations")
    }

    with op.batch_alter_table("evaluations") as batch_op:
        if "weight_post_measurement_id" in columns:
            batch_op.drop_constraint(
                "fk_evaluations_weight_post_measurement_id_measurements",
                type_="foreignkey",
            )
            batch_op.drop_column("weight_post_measurement_id")

        if "weight_pre_measurement_id" in columns:
            batch_op.drop_constraint(
                "fk_evaluations_weight_pre_measurement_id_measurements",
                type_="foreignkey",
            )
            batch_op.drop_column("weight_pre_measurement_id")

        if "piece_ref_id" in columns:
            batch_op.drop_constraint(
                "fk_evaluations_piece_ref_id_pieces",
                type_="foreignkey",
            )
            batch_op.drop_index("ix_evaluations_piece_ref_id")
            batch_op.drop_column("piece_ref_id")

    if "pieces" in tables:
        op.drop_index("ix_pieces_lot_id", table_name="pieces")
        op.drop_table("pieces")
