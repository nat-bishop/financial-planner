from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Category, Transaction
from app.schemas import CategoryCreate, CategoryResponse, CategoryUpdate

router = APIRouter()


@router.get("/", response_model=list[CategoryResponse])
async def list_categories(
    db: AsyncSession = Depends(get_db),
) -> list[Category]:
    """List all categories."""
    result = await db.scalars(
        select(Category).order_by(Category.name)
    )
    return list(result.all())


@router.post("/", response_model=CategoryResponse, status_code=201)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
) -> Category:
    """Create a custom category."""
    existing = await db.scalar(
        select(Category).where(Category.name == data.name)
    )
    if existing:
        raise HTTPException(status_code=400, detail="Category already exists")

    category = Category(name=data.name, description=data.description, exclude_from_totals=data.exclude_from_totals)
    db.add(category)
    await db.flush()
    return category


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    update: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
) -> Category:
    """Update a category's settings (e.g., exclude_from_totals)."""
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    return category


@router.delete("/{category_id}")
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a custom category. Default categories cannot be deleted.

    Transactions with this category will have their category set to NULL.
    """
    category = await db.get(Category, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    if category.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default categories")

    # Reset category on affected transactions (bulk update)
    await db.execute(
        update(Transaction)
        .where(Transaction.category == category.name)
        .values(category="Uncategorized", categorize_confidence=None)
    )

    await db.delete(category)
    return {"status": "deleted"}
