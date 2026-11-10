"""Runner adapters share planning and execution contracts, independent of editors."""
from .base import Adapter, Context, Plan, Policy
from .python import PytestAdapter, UnittestAdapter
from .javascript import NodeAdapter, VitestAdapter, JestAdapter

ADAPTERS: tuple[Adapter, ...] = (
    PytestAdapter(), UnittestAdapter(), NodeAdapter(), VitestAdapter(), JestAdapter(),
)
