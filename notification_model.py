
from datetime import date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (
    backref,
    relationship,
    scoped_session,
    sessionmaker,
)
from sqlalchemy.sql.expression import cast

from config import NOTIF_DB_URI, DB_DEBUG

engine = create_engine(NOTIF_DB_URI, echo=DB_DEBUG)
session = scoped_session(sessionmaker(autocommit=False,
                                      autoflush=False,
                                      bind=engine))
Base = declarative_base()
Base.query = session.query_property()


class Subscriber(Base):
    __tablename__ = 'subscriber'

    id = Column(Integer, primary_key=True)
    email = Column(String(64))
    activation_key = Column(String(64))
    deactivation_key = Column(String(64))
    group_id = Column(Integer, ForeignKey("group.id"))
    group = relationship('Group', foreign_keys=[group_id], backref="subscribers", single_parent=True)
    added = Column(Date, default=date.today)

    def __unicode__(self):
        return '%s [%s]' % (self.email, 'active' if not self.activation_key else 'inactive')

    def __repr__(self):
        return repr(self.__unicode__())


class Item(Base):
    __tablename__ = 'item'

    id = Column(Integer, primary_key=True)
    name = Column(String(64))
    type = Column(String(64))
    activation_key = Column(String(64))
    deactivation_key = Column(String(64))
    group_id = Column(Integer, ForeignKey("group.id"))
    group = relationship('Group', foreign_keys=[group_id], backref="items", single_parent=True)
    added = Column(Date, default=date.today)


    def __unicode__(self):
        return '%s:%s [%s]' % (self.type, self.name, 'active' if not self.activation_key else 'inactive')

    def __repr__(self):
        return repr(self.__unicode__())


class Group(Base):
    __tablename__ = 'group'

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True)
    activation_key = Column(String(64))
    created = Column(Date, default=date.today)

    def __unicode__(self):
        return '%s (%s) - subscribers: {%s} items {%s}' % (
            self.name,
            'active' if not self.activation_key else 'inactive',
            ', '.join(map(str, self.subscribers)),
            ', '.join(map(str, self.items)),
        )

    def __repr__(self):
        return repr(self.__unicode__())


if __name__ == '__main__':
    from sys import argv, exit
    if len(argv) == 1:
        print('Invalid action (init/migrate/cleanup)')
        exit(1)

    if argv[1] == 'migrate':
        print("Creating database")
        try:
            Base.metadata.create_all(engine, checkfirst=True)
            print("Database created")
            from IPython import embed; embed()
        except Exception as e:
            print("[E] Failed to create database: {0}".format(e))
    elif argv[1] == 'migrate':
        infile = argv[2]
        print("Migrating", infile)
        from json import load
        with open(infile, 'rb') as of:
            data = load(of)
            for item in data:
                if not item['active_emails'] or not item['dossiers']:
                    continue

                print('Migrating', item['id'], item['active_emails'], item['dossiers'])

                group = session.query(Group).filter(Group.name==item['id']).first() or Group(name=item['id'])

                for mail in item['active_emails']:
                    s = Subscriber(email)
                    session.add(s)
                    session.commit()
                    group.subscribers.append(s)

                for d in item['dossiers']:
                    i = Item(name=d, type='dossier')
                    session.add(i)
                    session.commit()
                    group.items.append(s)

                session.add(group)
                session.commit()
    elif argv[1] == 'cleanup':
        from datetime import datetime, timedelta
        for i in  session.query(Subscriber).filter(Subscriber.activation_key!='').filter(Subscriber.added<datetime.now()-timedelta(weeks=1)).all():
            session.delete(i)
            session.commit()
        for i in  session.query(Item).filter(Item.activation_key!='').filter(Item.added<datetime.now()-timedelta(weeks=1)).all():
            session.delete(i)
            session.commit()
        for i in  session.query(Group).filter(Group.activation_key!='').filter(Group.created<datettme.now()-timedelta(weeks=1)).all():
            if i.subscribers or i.items:
                continue
            session.delete(i)
            session.commit()
    else:
        print('unknown action')
