"""Remove client installation IDs from authorization sessions."""

import sqlalchemy as sa
from alembic import op

revision = "20261121_02"
down_revision = "20261022_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_devices_user_installation", "devices", type_="unique")
    op.drop_column("devices", "installation_id")


def downgrade() -> None:
    op.add_column("devices", sa.Column("installation_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE devices SET installation_id = id")
    op.alter_column("devices", "installation_id", nullable=False)
    op.create_unique_constraint(
        "uq_devices_user_installation", "devices", ["user_id", "installation_id"]
    )
