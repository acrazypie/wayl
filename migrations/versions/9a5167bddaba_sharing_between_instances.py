"""sharing between instances

Adds share links (playlists.share_token, share_settings) and subscriptions to other instances'
share links. New tables and one nullable column: safe on existing databases. Reviewed by hand:
the share_token uniqueness is a named unique index so the downgrade can drop it on SQLite.

Revision ID: 9a5167bddaba
Revises: c9e254420b47
Create Date: 2026-11-18 19:09:18.230581

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9a5167bddaba'
down_revision = 'c9e254420b47'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('share_settings',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('profile_share_token', sa.String(length=32), nullable=True),
    sa.Column('share_listens', sa.Boolean(), nullable=False),
    sa.Column('share_top_artists', sa.Boolean(), nullable=False),
    sa.Column('display_name', sa.String(length=60), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('profile_share_token')
    )
    op.create_table('subscriptions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('owner_name', sa.String(length=60), nullable=True),
    sa.Column('payload', sa.Text(), nullable=False),
    sa.Column('etag', sa.String(length=200), nullable=True),
    sa.Column('last_modified', sa.String(length=100), nullable=True),
    sa.Column('fetched_at', sa.DateTime(), nullable=True),
    sa.Column('checked_at', sa.DateTime(), nullable=True),
    sa.Column('last_error', sa.String(length=300), nullable=True),
    sa.Column('error_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['parent_id'], ['subscriptions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'url')
    )
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_subscriptions_parent_id'), ['parent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_subscriptions_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('playlists', schema=None) as batch_op:
        batch_op.add_column(sa.Column('share_token', sa.String(length=32), nullable=True))
        batch_op.create_index('ix_playlists_share_token', ['share_token'], unique=True)


def downgrade():
    with op.batch_alter_table('playlists', schema=None) as batch_op:
        batch_op.drop_index('ix_playlists_share_token')
        batch_op.drop_column('share_token')

    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_subscriptions_user_id'))
        batch_op.drop_index(batch_op.f('ix_subscriptions_parent_id'))

    op.drop_table('subscriptions')
    op.drop_table('share_settings')
