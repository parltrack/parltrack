from datetime import date
from json import dumps

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Date,
    Float,
    Boolean,
    Text,
    String,
    ForeignKey,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import (
    backref,
    relationship,
    scoped_session,
    sessionmaker,
)
from sqlalchemy.sql.expression import cast

from config import SQLALCHEMY_DATABASE_URI, DB_DEBUG

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()

def json_serializer(o):
    return dumps(o, default=dateJSONhandler)

engine = create_engine(SQLALCHEMY_DATABASE_URI,
                       echo=DB_DEBUG,
                       json_serializer=json_serializer)
session = scoped_session(sessionmaker(autocommit=False,
                                      autoflush=False,
                                      bind=engine))
Base = declarative_base()
Base.query = session.query_property()


CURRENT_MAGIC_VAL = date(9999, 12, 31)


class TimePeriod(Base):
    """
    Helper base class used on M2M intermediary models representing a
    relationship between a Representative and a Role (Group/Delegation/etc.)
    during a certain period in time.
    """
    __abstract__ = True

    id = Column(Integer, primary_key=True)
    begin = Column(Date)
    end = Column(Date)

    def is_current(self):
        if self.end == CURRENT_MAGIC_VAL:
            return True
        else:
            return False

    def is_past(self):
        if self.end < date.today():
            return True
        else:
            return False


class Country(Base):
    __tablename__ = 'country'

    id = Column(Integer, primary_key=True)
    code = Column(String(2), unique=True)
    name = Column(String(30), unique=True)

    def __unicode__(self):
        return u"%s - %s" % (self.code, self.name)


class Group(Base):
    __tablename__ = 'group'

    id = Column(Integer, primary_key=True)
    abbreviation = Column(String(10), unique=True)
    name = Column(String(100), unique=True)

    def __unicode__(self):
        return u"%s - %s" % (self.abbreviation, self.name)


class Committee(Base):
    __tablename__ = 'committee'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    abbreviation = Column(String(30), unique=True)


class Building(Base):
    """ A building of the European Parliament"""
    __tablename__ = 'building'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    abbreviation = Column(String(255), unique=True)
    street = Column(String(255))
    postcode = Column(String(255))

    def _town(self):
        return "bxl" if self.postcode == "1047" else "stg"

    def __unicode__(self):
        return u"%s - %s - %s - %s" % (self.id, self.name, self.street, self.postcode)

    @staticmethod
    def get_by_id(id):
        # TODO
        return

    @staticmethod
    def get_by_src(src):
        # TODO
        return

    @staticmethod
    def upsert(dossier_data):
        # TODO
        return

    @staticmethod
    def load(dossier_data):
        # TODO
        return


class Organization(Base):
    __tablename__ = 'organization'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)

    def __unicode__(self):
        return self.name


class Delegation(Base):
    __tablename__ = 'delegation'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))

    def __unicode__(self):
        return self.name


class MEP(Base):
    __tablename__ = 'mep'

    id = Column(Integer, primary_key=True)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    last_name_with_prefix = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    swaped_name = Column(String(255))
    gender = Column(String(2))
    birth_date = Column(Date)
    birth_place = Column(String(255))
    active = Column(Boolean)
    ep_id = Column(Integer, unique=True)
    total_score = Column(Float)
    twitter = Column(String(511))
    facebook = Column(String(511))
    ep_opinions = Column(String(4095))
    ep_debates = Column(String(4095))
    ep_questions = Column(String(4095))
    ep_declarations = Column(String(4095))
    ep_reports = Column(String(4095))
    ep_motions = Column(String(4095))
    ep_webpage = Column(String(4095))
    bxl_floor = Column(String(255))
    bxl_office_number = Column(String(255))
    bxl_fax = Column(String(255))
    bxl_phone1 = Column(String(255))
    bxl_phone2 = Column(String(255))
    stg_floor = Column(String(255))
    stg_office_number = Column(String(255))
    stg_fax = Column(String(255))
    stg_phone1 = Column(String(255))
    stg_phone2 = Column(String(255))
    stg_building_id = Column(Integer, ForeignKey(Building.id))
    stg_building = relationship(
        Building,
        foreign_keys="MEP.stg_building_id",
    )
    bxl_building_id = Column(Integer, ForeignKey(Building.id))
    bxl_building = relationship(
        Building,
        foreign_keys="MEP.bxl_building_id",
    )
    groups = relationship(Group, secondary='GroupMEP', lazy='dynamic')
    countries = relationship(Country, secondary='CountryMEP', lazy='dynamic')
    delegations = relationship(Delegation, secondary='DelegationRole', lazy='dynamic')
    committees = relationship(Committee, secondary='CommitteeRole', lazy='dynamic')
    organizations = relationship(Organization, secondary='OrganizationMEP', lazy='dynamic')
    #posts = GenericRelation(Post)

    def age(self):
        if date.today().month > self.birth_date.month:
            return date.today().year - self.birth_date.year
        elif date.today().month == self.birth_date.month and date.today().day > self.birth_date.day:
            return date.today().year - self.birth_date.year

    @staticmethod
    def get_by_id(id):
        # TODO
        return

    @staticmethod
    def get_by_name(name):
        # TODO
        return

    @staticmethod
    def upsert(mep_data):
        # TODO
        return

    def bxl_office(self):
        return self.bxl_floor + self.bxl_office_number

    def stg_office(self):
        return self.stg_floor + self.stg_office_number

    def __unicode__(self):
        return u"%s %s" % (self.first_name, self.last_name)


    @staticmethod
    def load(mep_data):
        mep_id = mep_data.get('UserID')
        session.add(Mep(id=mep_id, data=mep_data))


class GroupMEP(TimePeriod):
    __tablename__ = 'group_mep'

    mep_id = Column(Integer, ForeignKey(MEP.id), primary_key=True)
    group_id = Column(Integer, ForeignKey(Group.id), primary_key=True)
    role = Column(String(255))

    def __unicode__(self):
        return u"%s %s [%s]" % (self.mep.first_name, self.mep.last_name, self.group.abbreviation)


class DelegationRole(TimePeriod):
    __tablename__ = 'delegation_role'

    mep_id = Column(Integer, ForeignKey(MEP.id), primary_key=True)
    delegation_id = Column(Integer, ForeignKey(Delegation.id), primary_key=True)
    role = Column(String(255))

    def __unicode__(self):
        return u"%s : %s" % (self.mep.full_name, self.delegation)


class CommitteeRole(TimePeriod):
    __tablename__ = 'committee_role'

    mep_id = Column(Integer, ForeignKey(MEP.id), primary_key=True)
    committee_id = Column(Integer, ForeignKey(Committee.id), primary_key=True)
    role = Column(String(255))

    def __unicode__(self):
        return u"%s : %s" % (self.committee.abbreviation, self.mep.full_name)


class PostalAddress(TimePeriod):
    __tablename__ = 'postal_address'

    id = Column(Integer, primary_key=True)
    addr = Column(String(255))
    mep_id = Column(Integer, ForeignKey(MEP.id))
    mep = relationship(
        MEP,
        foreign_keys="PostalAddress.mep_id",
        backref=backref('postal_addresses', lazy='dynamic'),
    )


class Party(Base):
    __tablename__ = 'party'

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    country_id = Column(Integer, ForeignKey(Country.id))
    country = relationship(
        Country,
        foreign_keys="Party.country_id",
        backref=backref('parties', lazy='dynamic'),
    )

    def __unicode__(self):
        return self.name


class CountryMEP(TimePeriod):
    __tablename__ = 'country_mep'

    mep_id = Column(Integer, ForeignKey(MEP.id), primary_key=True)
    group_id = Column(Integer, ForeignKey(Group.id), primary_key=True)
    country_id = Column(Integer, ForeignKey(Country.id), primary_key=True)

    def __unicode__(self):
        return u"%s %s - %s" % (self.mep.first_name, self.mep.last_name, self.country.code)


class OrganizationMEP(TimePeriod):
    __tablename__ = 'organization_mep'

    mep_id = Column(Integer, ForeignKey(MEP.id), primary_key=True)
    organization_id = Column(Integer, ForeignKey(Organization.id), primary_key=True)
    role = Column(String(255))


class Assistant(Base):
    __tablename__ = 'assistant'

    id = Column(Integer, primary_key=True)
    full_name = Column(String(255))

    def __unicode__(self):
        return self.full_name


class AssistantMEP(Base):
    __tablename__ = 'assistant_mep'

    mep_id = Column(Integer, ForeignKey(MEP.id), primary_key=True)
    committee_id = Column(Integer, ForeignKey(Assistant.id), primary_key=True)
    type = Column(String(255))


class Email(Base):
    __tablename__ = 'email'

    id = Column(Integer, primary_key=True)
    email = Column(String(255))
    mep_id = Column(Integer, ForeignKey(MEP.id))
    mep = relationship(
        MEP,
        foreign_keys="Email.mep_id",
        backref=backref('emails', lazy='dynamic'),
    )

    def __unicode__(self):
        return self.email


class CV(Base):
    __tablename__ = 'cv'

    id = Column(Integer, primary_key=True)
    title = Column(Text)
    mep_id = Column(Integer, ForeignKey(MEP.id))
    mep = relationship(
        MEP,
        foreign_keys="CV.mep_id",
        backref=backref('cvs', lazy='dynamic'),
    )

    def __unicode__(self):
        return self.title


class WebSite(Base):
    __tablename__ = 'website'

    id = Column(Integer, primary_key=True)
    url = Column(String(4095))
    mep_id = Column(Integer, ForeignKey(MEP.id))
    mep = relationship(
        MEP,
        foreign_keys='WebSite.mep_id',
        backref=backref('websites', lazy='dynamic'),
    )

    def __unicode__(self):
        return self.url or u'-'


class PartyMEP(TimePeriod):
    __tablename__ = 'party_mep'

    mep_id = Column(Integer, ForeignKey(MEP.id), primary_key=True)
    party_id = Column(Integer, ForeignKey(Party.id), primary_key=True)
    role = Column(String(255))
    current = Column(Boolean)


#class Motion(models.Model):
#    meps = models.ManyToManyField(MEP)
#    title = models.TextField()
#    url = models.URLField(null=True)
#    date = models.DateField()
#    term = models.IntegerField()
#    posts = GenericRelation(Post)
#
#    def __unicode__(self):
#        return u"%s -- by -- %s" % (self.title, ', '.join(x.full_name for x in self.meps.all()))

LANGUAGES = [
    ("bg", u"български"),
    ("es", u"español"),
    ("cs", u"čeština"),
    ("da", u"dansk"),
    ("de", u"Deutsch"),
    ("et", u"eesti keel"),
    ("el", u"ελληνικά"),
    ("en", u"English"),
    ("fr", u"français"),
    ("ga", u"Gaeilge"),
    ("hr", u"hrvatski"),
    ("it", u"italiano"),
    ("lv", u"latviešu valoda"),
    ("lt", u"lietuvių kalba"),
    ("hu", u"magyar"),
    ("mt", u"Malti"),
    ("nl", u"Nederlands"),
    ("pl", u"polski"),
    ("pt", u"português"),
    ("ro", u"română"),
    ("sk", u"slovenčina"),
    ("sl", u"slovenščina "),
    ("fi", u"suomi"),
    ("sv", u"svenska")]


#class Question(Base):
#    mep = models.ForeignKey(MEP)
#    title = models.TextField()
#    text = models.TextField(null=True)
#    url = models.URLField(null=True)
#    date = models.DateField()
#    term = models.IntegerField()
#    lang = models.CharField(max_length=2, choices=LANGUAGES, default='en')
#    posts = GenericRelation(Post)
#
#    def __unicode__(self):
#        return u"%s: %s" % (self.mep, self.title)
#
#
#class Speech(models.Model):
#    mep = models.ForeignKey(MEP)
#    title = models.TextField()
#    text = models.TextField(null=True)
#    url = models.URLField(null=True)
#    date = models.DateField()
#    term = models.IntegerField()
#    lang = models.CharField(max_length=2, choices=LANGUAGES, default='en')
#    posts = GenericRelation(Post)
#
#    def __unicode__(self):
#        return u"%s: %s" % (self.mep, self.title)


class Subject(Base):
    __tablename__ = 'subject'

    id = Column(Integer, primary_key=True)
    code = Column(String(32))
    subject = Column(String(256))
    #posts = GenericRelation(Post)

    def __unicode__(self):
        return u"%s - %s" % (self.code, self.subject)


class Dossier(Base):
    __tablename__ = 'dossier'

    id = Column(Integer, primary_key=True)
    reference = Column(String(32))
    subjects = relationship(Subject, secondary='SubjectDossier', lazy='dynamic')
    #posts = GenericRelation(Post)

    def __unicode__(self):
        return self.reference


class SubjectDossier(TimePeriod):
    __tablename__ = 'subject_dossier'

    subject_id = Column(Integer, ForeignKey(Subject.id), primary_key=True)
    dossier_id = Column(Integer, ForeignKey(Dossier.id), primary_key=True)


class Rapporteur(Base):
    __tablename__ = 'rapporteur'

    id = Column(Integer, primary_key=True)
    #TYPES = (
    #    (0, 'REPORT'),
    #    (1, 'REPORT-SHADOW'),
    #    (2, 'COMPARL'),
    #    (3, 'COMPARL-SHADOW'),
    #)
    #TYPEMAP = { v: k for k, v in TYPES }
    mep_id = Column(Integer, ForeignKey(MEP.id))
    mep = relationship(
        MEP,
        foreign_keys="Rapporteur.mep_id",
        backref=backref('rapporteurs', lazy='dynamic'),
    )
    dossier_id = Column(Integer, ForeignKey(Dossier.id))
    dossier = relationship(
        Dossier,
        foreign_keys="Dossier.dossier_id",
        backref=backref('rapporteurs', lazy='dynamic'),
    )
    title = Column(Text)
    type = Column(Integer)
    url = Column(String(4096))
    date = Column(Date)
    term = Column(Integer)
    #posts = GenericRelation(Post)

    def __unicode__(self):
        return u"%s - %s - %s" % (self.mep, TYPEMAP[self.type], self.title)


class Amendment(Base):
    __tablename__ = 'amendment'

    id = Column(Integer, primary_key=True)
    dossier_id = Column(Integer, ForeignKey(Dossier.id))
    dossier = relationship(
        Dossier,
        foreign_keys="Dossier.dossier_id",
        backref=backref('amendments', lazy='dynamic'),
    )
    meps = relationship(Delegation, secondary='AmendmentMEP', lazy='dynamic')
    committees = relationship(Delegation, secondary='AmendmentCommittee', lazy='dynamic')
    old = Column(Text)
    new = Column(Text)
    url = Column(Text)
    seq = Column(Integer)
    date = Column(Date)
    location = Column(String(255))
    #posts = GenericRelation(Post)

    def __unicode__(self):
        return u"#%s %s" % (self.seq, self.dossier)


class AmendmentMEP(Base):
    __tablename__ = 'amendment_mep'

    amendment_id = Column(Integer, ForeignKey(Amendment.id), primary_key=True)
    mep_id = Column(Integer, ForeignKey(MEP.id), primary_key=True)


class AmendmentCommittee(Base):
    __tablename__ = 'amendment_committee'

    amendment_id = Column(Integer, ForeignKey(Amendment.id), primary_key=True)
    committee_id = Column(Integer, ForeignKey(Committee.id), primary_key=True)
#
#
#class Tweet(models.Model):
#    mep = models.ForeignKey(MEP)
#    text = models.TextField()
#    tweetid = models.CharField(max_length=32, unique=True)
#    date = models.DateField()
#    location = models.CharField(max_length=255, null=True)
#    geo = models.CharField(max_length=255, null=True)
#    posts = GenericRelation(Post)
#
#    def __unicode__(self):
#        return self.text


if __name__ == '__main__':
    print("Creating database")
    try:
        Base.metadata.create_all(engine, checkfirst=True)
        print("Database created")
    except Exception as e:
        print("[E] Failed to create database: {0}".format(e))
