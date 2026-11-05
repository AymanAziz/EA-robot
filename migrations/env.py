from alembic import context
from papertrade.config import Settings
from papertrade.db import Database
from papertrade.models import Base

db = Database(Settings())
if context.is_offline_mode():
    context.configure(url=db.settings.database_url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with db.engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
