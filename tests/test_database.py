import sys
import pytest

sys.path.insert(0, '67')
import database as db_module


@pytest.mark.asyncio
async def test_create_and_fetch_product(tmp_path):
    db_path = tmp_path / "test.db"
    db = db_module.Database(str(db_path))
    await db.initialize()

    pid = await db.create_product(name='Test', description='Desc', price=1.23, delivery_content='key')
    assert pid is not None

    prod = await db.fetch_product_by_id(pid)
    assert prod is not None
    assert prod['name'] == 'Test'
