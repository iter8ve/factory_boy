# -*- coding: utf-8 -*-
# Copyright: See the LICENSE file.

from __future__ import unicode_literals

from . import base
import warnings
import sqlalchemy

SESSION_PERSISTENCE_COMMIT = 'commit'
SESSION_PERSISTENCE_FLUSH = 'flush'
SESSION_PERSISTENCE_MERGE = 'merge'
SESSION_PERSISTENCE_CHECK_AND_MERGE = 'check'
SESSION_PERSISTENCE_GET_OR_ADD = 'get'
SESSION_PERSISTENCE_ADD = 'add'

VALID_SESSION_PERSISTENCE_TYPES = [
    None,
    SESSION_PERSISTENCE_COMMIT,
    SESSION_PERSISTENCE_FLUSH,
    SESSION_PERSISTENCE_MERGE,
    SESSION_PERSISTENCE_CHECK_AND_MERGE,
    SESSION_PERSISTENCE_GET_OR_ADD,
    SESSION_PERSISTENCE_ADD
]

from sqlalchemy import inspect


class SQLAlchemyOptions(base.FactoryOptions):
    def _check_sqlalchemy_session_persistence(self, meta, value):
        if value not in VALID_SESSION_PERSISTENCE_TYPES:
            raise TypeError(
                "%s.sqlalchemy_session_persistence must be one of %s, got %r" %
                (meta, VALID_SESSION_PERSISTENCE_TYPES, value)
            )

    def _check_force_flush(self, meta, value):
        if value:
            warnings.warn(
                "%(meta)s.force_flush has been deprecated as of 2.8.0 and will be removed in 3.0.0. "
                "Please set ``%(meta)s.sqlalchemy_session_persistence = 'flush'`` instead."
                % dict(meta=meta),
                DeprecationWarning,
                # Stacklevel:
                # declaration -> FactoryMetaClass.__new__ -> meta.contribute_to_class
                # -> meta._fill_from_meta -> option.apply -> option.checker
                stacklevel=6,
            )

    def _build_default_options(self):
        return super(SQLAlchemyOptions, self)._build_default_options() + [
            base.OptionDefault('sqlalchemy_session', None, inherit=True),
            base.OptionDefault(
                'sqlalchemy_session_persistence',
                None,
                inherit=True,
                checker=self._check_sqlalchemy_session_persistence,
            ),

            # DEPRECATED as of 2.8.0, remove in 3.0.0
            base.OptionDefault(
                'force_flush',
                False,
                inherit=True,
                checker=self._check_force_flush,
            ),

            base.OptionDefault(
                'sqlalchemy_update_existing',
                False, inherit=True
            )
        ]

def attr_dict(instance):
    return {
        k: v for k, v in instance.__dict__.items()
            if not k.startswith('_sa')
    }


class SQLAlchemyModelFactory(base.Factory):
    """Factory for SQLAlchemy models. """

    _options_class = SQLAlchemyOptions

    class Meta:
        abstract = True

    @staticmethod
    def find_existing(session, obj, model_cls):
        constraints = [
            c for c in model_cls.__table__.constraints
                if isinstance(c, sqlalchemy.UniqueConstraint)
        ]
        for const in constraints:
            for col in const.columns:
                attr = getattr(obj, col.key, None)
                if attr:
                    matching_col = getattr(model_cls, col.key, None)
                    if matching_col:
                        existing = session.query(model_cls).\
                            filter(matching_col==attr).first()
                        if existing:
                            return existing

    @staticmethod
    def update_existing(session, obj, existing):
        for k, v in attr_dict(existing).items():
            obj_attr = getattr(obj, k, None)
            if obj_attr and obj_attr != v:
                setattr(existing, k, obj_attr)
        return existing

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Create an instance of the model, and save it to the database."""
        session = cls._meta.sqlalchemy_session
        session_persistence = cls._meta.sqlalchemy_session_persistence
        if cls._meta.force_flush:
            session_persistence = SESSION_PERSISTENCE_FLUSH

        obj = model_class(*args, **kwargs)
        if session is None:
            raise RuntimeError("No session provided.")

        if session_persistence == SESSION_PERSISTENCE_MERGE:
            obj = session.merge(obj)
            session.commit()
        elif session_persistence in \
                ('check', SESSION_PERSISTENCE_CHECK_AND_MERGE):
            existing = cls.find_existing(session, obj, model_class)
            if existing:
                if cls._meta.sqlalchemy_update_existing:
                    existing = cls.update_existing(session, obj, existing)
                    existing = session.merge(existing)
                    session.flush()
                return existing
            obj = session.merge(obj)
            session.flush()
        elif session_persistence == SESSION_PERSISTENCE_GET_OR_ADD:
            existing = cls.find_existing(session, obj, model_class)
            if existing:
                session.merge(existing)
                return existing
            else:
                session.add(obj)
                session.commit()
        elif session_persistence == SESSION_PERSISTENCE_FLUSH:
            session.flush()
        elif session_persistence == SESSION_PERSISTENCE_COMMIT:
            session.commit()
        elif session_persistence == SESSION_PERSISTENCE_ADD:
            session.add(obj)

        return obj
