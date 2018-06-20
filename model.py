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
    name = Column(String(512), unique=True)
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


class Staff(Base):
    __tablename__ = 'staff'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)

    def __unicode__(self):
        return u"%s - %s" % (self.code, self.name)


class MEP(Base):
    __tablename__ = 'mep'

    id = Column(Integer, primary_key=True)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    last_name_with_prefix = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    photo = Column(String(4095))
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
    #groups = relationship(Group, secondary='GroupMEP', lazy='dynamic')
    #countries = relationship(Country, secondary='CountryMEP', lazy='dynamic')
    #delegations = relationship(Delegation, secondary='DelegationRole', lazy='dynamic')
    #committees = relationship(Committee, secondary='CommitteeRole', lazy='dynamic')
    #organizations = relationship(Organization, secondary='OrganizationMEP', lazy='dynamic')
    #staff = relationship(Staff, secondary='StaffRole', lazy='dynamic')
    #posts = GenericRelation(Post)

    @staticmethod
    def upsert(mep_data):
        mep = MEP.get_by_id(mep_data['UserId'])
        if not mep:
            return MEP.insert(mep_data)
        # TODO
        return mep

    @staticmethod
    def insert(d):
        mep = MEP(
            ep_id=d.get('UserId', d['UserID']),
            first_name=d['Name']['sur'],
            last_name=d['Name']['family'],
            last_name_with_prefix=d['Name']['familylc'],
            full_name=d['Name']['full'],
            gender=d.get('Gender', ''),
            photo=d['Photo'],
            facebook=d['Facebook'][0] if len(d.get('Facebook', [])) else '',
            twitter=d['Twitter'][0] if len(d.get('Twitter', [])) else '',
        )

        if 'Birth' in d:
            mep.birth_date=d['Birth'].get('date')
            mep.birth_place=d['Birth'].get('place', '')

        mep.aliases = [MEPAlias(mep_id=mep.id, alias=a) for a in d['Name']['aliases']]
        mep.cvs = [CV(mep_id=mep.id, title=a) for a in d.get('cv', {}).values()]
        mep.emails = [Email(mep_id=mep.id, email=e) for e in d.get('Mail', [])]

        for c in d.get('Committees', []):
            name = c['Organization']
            com = session.query(Committee).filter(Committee.name==name).first()
            if not com:
                com = Committee(name=name, abbreviation=c['abbr'])
                session.add(com)
                session.commit()

            mep.committees.append(CommitteeRole(
                mep_id=mep.id,
                committee_id=com.id,
                role=c['role'],
                begin=c['start'],
                end=c['end'],
            ))

        for dd in d.get('Delegations', []):
            name = dd['Organization']
            de = session.query(Delegation).filter(Delegation.name==name).first()
            if not de:
                de = Delegation(name=name)
                session.add(de)
                session.commit()

            mep.delegations.append(DelegationRole(
                mep_id=mep.id,
                delegation_id=de.id,
                role=dd['role'],
                begin=dd['start'],
                end=dd['end'],
            ))

        for g in d.get('Groups', []):
            name = g['Organization']
            abbr = g['groupid']
            if isinstance(abbr, list):
                abbr = abbr[0]
            gg = session.query(Group).filter(Group.abbreviation==abbr).first()
            if not gg:
                gg = Group(name=name, abbreviation=abbr)
                session.add(gg)
                session.commit()

            mep.groups.append(GroupMEP(
                mep_id=mep.id,
                group_id=gg.id,
                role=g['role'],
                begin=g['start'],
                end=g['end'],
            ))

        for s in d.get('Staff', []):
            name = s['Organization']
            ss = session.query(Staff).filter(Staff.name==name).first()
            if not ss:
                ss = Staff(name=name)
                session.add(ss)
                session.commit()

            mep.staff.append(StaffRole(
                mep_id=mep.id,
                staff_id=ss.id,
                role=s['role'],
                begin=s['start'],
                end=s['end'],
            ))

        for c in d.get('Constituencies', []):
            if not c:
                continue
            name = c['party']
            country = c['country']
            p = session.query(Party).filter(Party.name==name).first()
            if not p:
                country = session.query(Country).filter(Country.name==country).first()
                if not country:
                    # TODO Country.code
                    country = Country(name=country)
                    session.add(country)
                    session.commit()
                p = Party(name=name, country_id=country.id)
                session.add(p)
                session.commit()

            # TODO party role, is current
            mep.parties.append(PartyMEP(
                mep_id=mep.id,
                party_id=p.id,
                begin=c['start'],
                end=c['end'],
            ))

        if 'Addresses' in d:
            bxl = d['Addresses'].get('Brussels', {})
            stg = d['Addresses'].get('Strasbourg', {})
            mep.bxl_floor = bxl.get('Address', {}).get('Floor', '')
            mep.bxl_office_number = bxl.get('Address', {}).get('Office')
            mep.bxl_fax = bxl.get('Fax', '')
            mep.bxl_phone1 = bxl.get('Phone', '')
            mep.stg_floor = stg.get('Address', {}).get('Floor', '')
            mep.stg_office_number = stg.get('Address', {}).get('Office')
            mep.stg_fax = stg.get('Fax')
            mep.stg_phone1 = stg.get('Phone')



        # TODO Changelog, Activities
        return mep

    def age(self):
        if not self.birth_date:
            return
        if date.today().month > self.birth_date.month:
            return date.today().year - self.birth_date.year
        elif date.today().month == self.birth_date.month and date.today().day > self.birth_date.day:
            return date.today().year - self.birth_date.year
        return

    @staticmethod
    def get_by_id(ep_id):
        return session.query(MEP).filter(MEP.ep_id==ep_id).first()

    @staticmethod
    def get_by_name(name):
        # TODO
        return

    def bxl_office(self):
        return self.bxl_floor + self.bxl_office_number

    def stg_office(self):
        return self.stg_floor + self.stg_office_number

    def __unicode__(self):
        return u"%s %s" % (self.first_name, self.last_name)


class MEPAlias(Base):
    __tablename__ = 'mep_alias'

    id = Column(Integer, primary_key=True)
    mep_id = Column(Integer, ForeignKey(MEP.id))
    alias = Column(String(255))
    mep = relationship(
        MEP,
        foreign_keys="MEPAlias.mep_id",
        backref=backref('aliases', lazy='dynamic'),
    )

    def __unicode__(self):
        return self.alias


class GroupMEP(TimePeriod):
    __tablename__ = 'group_mep'

    mep_id = Column(Integer, ForeignKey(MEP.id))
    group_id = Column(Integer, ForeignKey(Group.id))
    role = Column(String(255))
    mep = relationship(
        MEP,
        foreign_keys="GroupMEP.mep_id",
        backref=backref('groups', lazy='dynamic'),
    )
    group = relationship(
        Group,
        foreign_keys="GroupMEP.group_id",
        backref=backref('meps', lazy='dynamic'),
    )

    def __unicode__(self):
        return u"%s %s [%s]" % (self.mep.first_name, self.mep.last_name, self.group.abbreviation)


class DelegationRole(TimePeriod):
    __tablename__ = 'delegation_role'

    mep_id = Column(Integer, ForeignKey(MEP.id))
    delegation_id = Column(Integer, ForeignKey(Delegation.id))
    role = Column(String(255))
    mep = relationship(
        MEP,
        foreign_keys="DelegationRole.mep_id",
        backref=backref('delegations', lazy='dynamic'),
    )
    delegation = relationship(
        Delegation,
        foreign_keys="DelegationRole.delegation_id",
        backref=backref('meps', lazy='dynamic'),
    )

    def __unicode__(self):
        return u"%s : %s" % (self.mep.full_name, self.delegation)


class StaffRole(TimePeriod):
    __tablename__ = 'staff_role'

    mep_id = Column(Integer, ForeignKey(MEP.id))
    staff_id = Column(Integer, ForeignKey(Staff.id))
    role = Column(String(255))
    mep = relationship(
        MEP,
        foreign_keys="StaffRole.mep_id",
        backref=backref('staff', lazy='dynamic'),
    )
    staff = relationship(
        Staff,
        foreign_keys="StaffRole.staff_id",
        backref=backref('meps', lazy='dynamic'),
    )

    def __unicode__(self):
        return u"%s : %s" % (self.committee.abbreviation, self.mep.full_name)


class CommitteeRole(TimePeriod):
    __tablename__ = 'committee_role'

    mep_id = Column(Integer, ForeignKey(MEP.id))
    committee_id = Column(Integer, ForeignKey(Committee.id))
    role = Column(String(255))
    mep = relationship(
        MEP,
        foreign_keys="CommitteeRole.mep_id",
        backref=backref('committees', lazy='dynamic'),
    )
    committee = relationship(
        Committee,
        foreign_keys="CommitteeRole.committee_id",
        backref=backref('meps', lazy='dynamic'),
    )

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

    mep_id = Column(Integer, ForeignKey(MEP.id))
    group_id = Column(Integer, ForeignKey(Group.id))
    country_id = Column(Integer, ForeignKey(Country.id))
    mep = relationship(
        MEP,
        foreign_keys="CountryMEP.mep_id",
        backref=backref('countries', lazy='dynamic'),
    )
    group = relationship(
        Group,
        foreign_keys="CountryMEP.group_id",
        backref=backref('countries', lazy='dynamic'),
    )
    country = relationship(
        Country,
        foreign_keys="CountryMEP.country_id",
        backref=backref('meps', lazy='dynamic'),
    )

    def __unicode__(self):
        return u"%s %s - %s" % (self.mep.first_name, self.mep.last_name, self.country.code)


class OrganizationMEP(TimePeriod):
    __tablename__ = 'organization_mep'

    mep_id = Column(Integer, ForeignKey(MEP.id))
    organization_id = Column(Integer, ForeignKey(Organization.id))
    role = Column(String(255))
    mep = relationship(
        MEP,
        foreign_keys="OrganizationMEP.mep_id",
        backref=backref('organizations', lazy='dynamic'),
    )
    organization = relationship(
        Organization,
        foreign_keys="OrganizationMEP.organization_id",
        backref=backref('meps', lazy='dynamic'),
    )


class Assistant(Base):
    __tablename__ = 'assistant'

    id = Column(Integer, primary_key=True)
    full_name = Column(String(255))

    def __unicode__(self):
        return self.full_name


class AssistantMEP(Base):
    __tablename__ = 'assistant_mep'

    id = Column(Integer, primary_key=True)
    mep_id = Column(Integer, ForeignKey(MEP.id))
    committee_id = Column(Integer, ForeignKey(Assistant.id))
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

    mep_id = Column(Integer, ForeignKey(MEP.id))
    party_id = Column(Integer, ForeignKey(Party.id))
    role = Column(String(255))
    current = Column(Boolean)
    mep = relationship(
        MEP,
        foreign_keys='PartyMEP.mep_id',
        backref=backref('parties', lazy='dynamic'),
    )
    party = relationship(
        Party,
        foreign_keys='PartyMEP.party_id',
        backref=backref('meps', lazy='dynamic'),
    )


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
    #subjects = relationship(Subject, secondary='SubjectDossier', lazy='dynamic')
    #posts = GenericRelation(Post)

    def __unicode__(self):
        return self.reference


class SubjectDossier(Base):
    __tablename__ = 'subject_dossier'

    id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, ForeignKey(Subject.id))
    dossier_id = Column(Integer, ForeignKey(Dossier.id))
    dossier = relationship(
        Dossier,
        foreign_keys="SubjectDossier.dossier_id",
        backref=backref('subjects', lazy='dynamic'),
    )
    subject = relationship(
        Subject,
        foreign_keys="SubjectDossier.subject_id",
        backref=backref('dossiers', lazy='dynamic'),
    )


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
        foreign_keys="Rapporteur.dossier_id",
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
        foreign_keys="Amendment.dossier_id",
        backref=backref('amendments', lazy='dynamic'),
    )
    #meps = relationship(MEP, secondary='AmendmentMEP', lazy='dynamic', foreign_keys="MEP.id")
    #committees = relationship(Committee, secondary='AmendmentCommittee', lazy='dynamic')
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

    id = Column(Integer, primary_key=True)
    amendment_id = Column(Integer, ForeignKey(Amendment.id))
    mep_id = Column(Integer, ForeignKey(MEP.id))
    mep = relationship(
        MEP,
        foreign_keys="AmendmentMEP.mep_id",
        backref=backref('amendments', lazy='dynamic'),
    )
    amendment = relationship(
        Amendment,
        foreign_keys="AmendmentMEP.amendment_id",
        backref=backref('meps', lazy='dynamic'),
    )


class AmendmentCommittee(Base):
    __tablename__ = 'amendment_committee'

    id = Column(Integer, primary_key=True)
    amendment_id = Column(Integer, ForeignKey(Amendment.id))
    committee_id = Column(Integer, ForeignKey(Committee.id), primary_key=True)
    amendment = relationship(
        Amendment,
        foreign_keys="AmendmentCommittee.amendment_id",
        backref=backref('committees', lazy='dynamic'),
    )
    committee = relationship(
        Committee,
        foreign_keys="AmendmentCommittee.committee_id",
        backref=backref('amendments', lazy='dynamic'),
    )
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
