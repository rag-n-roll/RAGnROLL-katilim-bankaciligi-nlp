"""Doğal dil sorgularını güvenli çalıştırma planlarına dönüştürür."""

from .compiler import DomainQueryCompiler, QueryPlan

__all__ = ["DomainQueryCompiler", "QueryPlan"]
