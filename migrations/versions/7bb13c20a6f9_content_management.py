"""Versioned landing-page content."""
from alembic import op
import sqlalchemy as sa
revision='7bb13c20a6f9'
down_revision='e3c411b370b1'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('content_pages',sa.Column('slug',sa.String(),primary_key=True),sa.Column('draft_id',sa.String(),nullable=False),sa.Column('published_id',sa.String(),nullable=False))
    op.create_table('content_revisions',sa.Column('id',sa.String(),primary_key=True),sa.Column('page_slug',sa.String(),sa.ForeignKey('content_pages.slug'),nullable=False),sa.Column('content',sa.JSON(),nullable=False),sa.Column('author_id',sa.String(),sa.ForeignKey('accounts.id')),sa.Column('reason',sa.String(),nullable=False),sa.Column('created_at',sa.String(),nullable=False))
    op.create_index('ix_content_revisions_page_slug','content_revisions',['page_slug'])

def downgrade():
    op.drop_index('ix_content_revisions_page_slug',table_name='content_revisions')
    op.drop_table('content_revisions')
    op.drop_table('content_pages')
