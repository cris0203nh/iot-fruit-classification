
"""AGROP-29 crear trazabilidad de piezas y pesajes.

Revision ID: 7ccb39e4d4d7
Revises:
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7ccb39e4d4d7"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Crear tabla de piezas.
    op.create_table(
        "pieces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lot_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["lot_id"], ["lots.id"],
            name="fk_pieces_lot_id_lots"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "lot_id", "code", name="uq_piece_lot_code"
        ),
    )

    op.create_index(
        "ix_pieces_lot_id", "pieces", ["lot_id"], unique=False
    )

    # 2. Agregar referencias a evaluaciones.
    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.add_column(
            sa.Column("piece_ref_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("weight_pre_measurement_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("weight_post_measurement_id", sa.Integer(), nullable=True)
        )

        batch_op.create_index(
            "ix_evaluations_piece_ref_id",
            ["piece_ref_id"],
            unique=False,
        )

        batch_op.create_foreign_key(
            "fk_evaluations_piece_ref_id_pieces",
            "pieces",
            ["piece_ref_id"],
            ["id"],
        )

        batch_op.create_foreign_key(
            "fk_evaluations_weight_pre_measurement_id_measurements",
            "measurements",
            ["weight_pre_measurement_id"],
            ["id"],
        )

        batch_op.create_foreign_key(
            "fk_evaluations_weight_post_measurement_id_measurements",
            "measurements",
            ["weight_post_measurement_id"],
            ["id"],
        )

    # 3. Migrar identificadores de piezas existentes.
    connection = op.get_bind()

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
                SELECT id FROM pieces
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
    # Revertir las nuevas referencias.
    with op.batch_alter_table("evaluations") as batch_op:
        batch_op.drop_constraint(
            "fk_evaluations_weight_post_measurement_id_measurements",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_evaluations_weight_pre_measurement_id_measurements",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_evaluations_piece_ref_id_pieces",
            type_="foreignkey",
        )

        batch_op.drop_index("ix_evaluations_piece_ref_id")

        batch_op.drop_column("weight_post_measurement_id")
        batch_op.drop_column("weight_pre_measurement_id")
        batch_op.drop_column("piece_ref_id")

    op.drop_index("ix_pieces_lot_id", table_name="pieces")
    op.drop_table("pieces")
