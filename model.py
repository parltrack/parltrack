import sys
from datetime import date, datetime
from json import dumps
from utils.utils import asDate, unws
import unicodedata

# TODO
# dossier loading
# changelog model (document id,  change type, prev value, cur value, path, # date)
# save handler to models which handles changelog

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
    UniqueConstraint
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

now = datetime.now

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
    abbr = Column(String(10), unique=True)
    name = Column(String(100), unique=True)

    def __unicode__(self):
        return u"%s - %s" % (self.abbr, self.name)


class Committee(Base):
    __tablename__ = 'committee'

    id = Column(Integer, primary_key=True)
    name = Column(String(512), unique=True)
    abbr  = Column(String(30))

class Building(Base):
    """ A building of the European Parliament"""
    __tablename__ = 'building'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)
    abbr = Column(String(255), unique=True)
    city = Column(String(255))
    street = Column(String(255))
    postcode = Column(String(255))

    __table_args__ = (UniqueConstraint('name', 'abbr', 'city', name='_building_uc'),)

    def __unicode__(self):
        return u"%s - %s - %s - %s" % (self.id, self.name, self.street, self.postcode)

    def __repr__(self):
        return u"%s - %s - %s" % (self.name, self.street, self.postcode)

    @staticmethod
    def get_by_id(id):
        # TODO
        return

    @staticmethod
    def upsert(dossier_data):
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
    abbr = Column(String(255))

    def __unicode__(self):
        return self.name


class Staff(Base):
    __tablename__ = 'staff'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True)

    def __unicode__(self):
        return u"%s - %s" % (self.code, self.name)


class Format(Base):
    """
    Abstract base class containing the format of MEP activities
    """
    __abstract__ = True

    id = Column(Integer, primary_key=True)
    language = Column(String(64))
    title = Column(String(4096))
    url = Column(String(255))
    pubRef = Column(String(100))
    type = Column(String(32))
    size = Column(Integer)


class MEP(Base):
    __tablename__ = 'mep'

    id = Column(Integer, primary_key=True)
    src_url = Column(String(1024), nullable=False)
    created = Column(Date, nullable=False)
    updated = Column(Date, nullable=False)
    first_name = Column(String(255), nullable=False)
    last_name = Column(String(255), nullable=False)
    last_name_with_prefix = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    photo = Column(String(4095))
    swaped_name = Column(String(255))
    gender = Column(String(2))
    birth_date = Column(Date)
    death_date = Column(Date)
    birth_place = Column(String(255))
    active = Column(Boolean)
    ep_id = Column(Integer, unique=True)
    total_score = Column(Float)
    twitter = Column(String(511))
    facebook = Column(String(511))
    homepage = Column(Text)
    #ep_opinions = Column(String(4095))
    #ep_debates = Column(String(4095))
    #ep_questions = Column(String(4095))
    #ep_declarations = Column(String(4095))
    #ep_reports = Column(String(4095))
    #ep_motions = Column(String(4095))
    #groups = relationship(Group, secondary='GroupMEP', lazy='dynamic')
    #countries = relationship(Country, secondary='CountryMEP', lazy='dynamic')
    #delegations = relationship(Delegation, secondary='DelegationRole', lazy='dynamic')
    #committees = relationship(Committee, secondary='CommitteeRole', lazy='dynamic')
    #organizations = relationship(Organization, secondary='OrganizationMEP', lazy='dynamic')
    #staff = relationship(Staff, secondary='StaffRole', lazy='dynamic')
    #posts = GenericRelation(Post)
    #offices = relationship(Office)
    #assistants = relationship(Assistant, secondary='AssistantMEP', lazy='dynamic')

    @staticmethod
    def upsert(mep_data):
        mep = MEP.get_by_id(mep_data['UserID'])
        if not mep:
            return MEP.insert(mep_data)
        # TODO
        return mep

    @staticmethod
    def insert(d):
        #if len(d.get('Facebook', [])) > 1: print >>sys.stderr, "more than 1 facebook entry", d['UserID'], d['Facebook'] 
        #if len(d.get('Twitter', [])) > 1: print  >>sys.stderr, "more than 1 Twitter entry", d['UserID'], d['Twitter'] 
        #if len(d.get('Homepage', [])) > 1: print  >>sys.stderr, "more than 1 Homepage entry", d['UserID'], d['Homepage'] 
        mep = MEP(
            ep_id=d['UserID'],
            first_name=d['Name']['sur'],
            last_name=d['Name']['family'],
            last_name_with_prefix=d['Name']['familylc'],
            full_name=d['Name']['full'],
            gender=d.get('Gender', ''),
            photo=d['Photo'],
            facebook=d['Facebook'][0] if len(d.get('Facebook', [])) else '',
            twitter=d['Twitter'][0] if len(d.get('Twitter', [])) else '',
            homepage=d['Homepage'][0] if len(d.get('Homepage', [])) else '', 
            created=d['meta'].get('created', now()),
            updated=d['meta'].get('updated', now()),
            src_url=d['meta'].get('url', ''),
        )

        if 'Birth' in d:
            mep.birth_date=asDate(d['Birth'].get('date'))
            mep.birth_place=d['Birth'].get('place', '')

        if 'Death' in d:
            mep.death_date=asDate(d['Death'])

        session.add(mep)
        session.commit()

        mep.aliases = [MEPAlias(mep_id=mep.id, alias=a) for a in d['Name']['aliases']]
        mep.cvs = [CV(mep_id=mep.id, title=a) for a in d.get('cv', {}).values()]
        mep.emails = [Email(mep_id=mep.id, email=e) for e in d.get('Mail', [])]

        for c in d.get('Committees', []):
            name = c['Organization']
            abbr = c['abbr']
            com = session.query(Committee).filter(Committee.name==name).first()
            if not com:
                com = Committee(name=name, abbr=abbr)
                session.add(com)
                session.commit()
            if com:
                mep.committees.append(CommitteeRole(
                    mep_id=mep.id,
                    committee_id=com.id,
                    role=c['role'],
                    begin=c['start'],
                    end=c['end'],
                ))

        for dd in d.get('Delegations', []):
            name = dd['Organization']
            abbr = dd['abbr']
            de = session.query(Delegation).filter(Delegation.name==name).first()
            if not de:
                de = Delegation(name=name, abbr=abbr)
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
            gg = session.query(Group).filter(Group.abbr==abbr).first()
            if not gg:
                gg = Group(name=name, abbr=abbr)
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
            country = session.query(Country).filter(Country.name==country).first()
            if not country:
                # TODO Country.code
                country = Country(name=country)
                session.add(country)
                session.commit()
            p = session.query(Party).filter(Party.name==name, Party.country==country).first()
            if not p:
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

        for k,a in d.get('Addresses', {}).items():
            if k == 'Postal':
                p =  PostalAddress(addr=' '.join(a), mep_id=mep.id)
                session.add(p)
            else:
                o = mep._add_office(a)
                o.mep_id = mep.id
                mep.offices.append(o)
            session.commit()

        for t, A in d.get('assistants', {}).items():
            for name in A:
                aa = session.query(Assistant).filter(Assistant.name==name).first()
                if not aa:
                    aa = Assistant(name=name)
                    session.add(aa)
                mep.assistants.append(AssistantMEP(
                    mep_id=mep.id,
                    assistant_id=aa.id,
                    type=t,
                ))
            session.commit()

        for u in d.get('Declarations of Participation', []):
            dop = session.query(PartDecl).filter(PartDecl.url==u, PartDecl.mep_id==mep.id).first()
            if not dop:
                dop = PartDecl(url=u, mep=mep)
                session.add(dop)
                mep.partdecls.append(dop)
            session.commit()

        MEP.insert_activities(mep, d.get("activities",{}))

        # TODO Changelog
        return mep

    def _add_office(self, office):
        b = office['Address']
        building = session.query(Building).filter(Building.abbr==b["building_code"]).first()
        if not building:
            building = Building(name=b['Building'],
                                abbr=b['building_code'],
                                street=b['Street'],
                                postcode=b.get('Zip', '') or '{0} ({1})'.format(b['Zip1'], b['Zip2']),
                                city=b['City'])
            session.add(building)
            session.commit()

        floor = on = ''
        o = b.get('Office', '')
        if o[0].isnumeric():
            for s in 'GEFGHKMYgCB':
                try:
                    floor, on = o.split(s)
                    break
                except:
                    pass
        else:
            on = o
        if not on:
            print('Invalid floor/on', b.get('Office'), self.id, self.ep_id, b)
        office = Office(floor=floor, office_number=on, fax=b.get('Fax', ''), phone1=b.get('Phone', ''), building_id=building.id)
        session.add(office)
        return office

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

    def __unicode__(self):
        return u"%s %s" % (self.first_name, self.last_name)

    def __repr__(self):
        return u"%s %s (%d)" % (self.first_name, self.last_name, self.ep_id)

    @staticmethod
    def insert_activities(mep, activities):
        for type, terms in activities.items():
            if type == "WDECL": continue
            if 'SHADOW' in type: shadow = True
            else: shadow = False
            for term, items in terms.items():
                for item in items:
                    # voteExplanationList in debatesis always an empty list in import, warn if not and adapt model accordingly
                    if type=="CRE" and item['voteExplanationList'] != []:
                        print("error: debate has a non-empty voteExplanationList:", d['voteExplanationList'], file=sys.stderr)
                        print(mep, file=sys.stderr)
                    # TODO did = session.query(Dossiers).filter(Dossier.reference==o['dossier'][0])
                    aa = session.query(Activity).filter(
                            Activity.type==type,
                            Activity.term==term,
                            Activity.title_url==item['titleUrl'],
                            Activity.displayLanguageWarning ==item['displayLanguageWarning'],
                            Activity.title==item['title'],
                            Activity.content==item['content'],
                            Activity.language==item['language'],
                            Activity.date==asDate(item['date']),
                            Activity.mep_id==mep.id,
                            Activity.shadow==shadow,
                            Activity.text==item.get('text'),
                            ).first()
                    if not aa:
                        aa = Activity(
                            type=type,
                            term=term,
                            title_url=item['titleUrl'],
                            displayLanguageWarning =item['displayLanguageWarning'],
                            title=item['title'],
                            content=item['content'],
                            language=item['language'],
                            date=asDate(item['date']),
                            mep_id=mep.id,
                            shadow=shadow,
                            text=item.get('text')
                        )
                        session.add(aa)
                        session.commit()
                    # add format list
                    for f in item.get('formatList',[]):
                        ff = session.query(ActivityFormat).filter(
                                ActivityFormat.language == f['language'],
                                ActivityFormat.title == f['title'],
                                ActivityFormat.url == f['url'],
                                ActivityFormat.pubRef == f['pubRef'],
                                ActivityFormat.type == f['type'],
                                ActivityFormat.size == f['size']
                                ).first()
                        if not ff:
                            ff = ActivityFormat(
                                    language=f['language'],
                                    title=f['title'],
                                    url=f['url'],
                                    pubRef=f['pubRef'],
                                    type=f['type'],
                                    size=f['size'],
                                    aid=aa.id
                                    )
                            session.add(ff)
                    # committeelist
                    for c in item.get('committeeList',[]):
                        name = c['title']
                        abbr = c['code']
                        cc = session.query(Committee).filter(Committee.name==name, abbr==abbr).first()
                        if not cc:
                            cc = Committee(name=name, abbr=abbr)
                            session.add(cc)
                            session.commit()
                        if not session.query(ActivityCommittee).filter(ActivityCommittee.aid==aa.id, ActivityCommittee.com_id==cc.id).first():
                            aa.committees.append(ActivityCommittee(aid=aa.id,com_id=cc.id))
                            session.commit()
                    # referencelist (strings)
                    for r in set(item.get('referenceList',[])):
                        rr = session.query(Reference).filter(Reference.reference==r).first()
                        if not rr:
                            rr = Reference(reference=r)
                            session.add(rr)
                            session.commit()
                        if not session.query(ActivityReference).filter(ActivityReference.aid==aa.id, ActivityReference.ref_id==rr.id).first():
                            aa.references.append(ActivityReference(aid=aa.id,ref_id=rr.id))
                            session.commit()
        session.commit()

        for term, declarations in activities.get("WDECL", {}).items():
            for d in declarations:
                dd = session.query(Declaration).filter(
                        Declaration.term==term,
                        Declaration.title_url==d['titleUrl'],
                        Declaration.displayLanguageWarning ==d['displayLanguageWarning'],
                        Declaration.title==d['title'],
                        Declaration.content==d['content'],
                        Declaration.language==d['language'],
                        Declaration.date==asDate(d['date']),
                        Declaration.mep_id==mep.id,
                        Declaration.pvReferenceActive == d['pvReferenceActive'],
                        Declaration.pvReferenceUrl    == d['pvReferenceUrl'],
                        Declaration.taReferenceUrl    == d['taReferenceUrl'],
                        Declaration.expiryDate        == asDate(d['expiryDate']),
                        Declaration.signatoryDate     == asDate(d['signatoryDate']),
                        Declaration.nbSignatory       == d['nbSignatory'],
                        Declaration.status            == d['status'],
                        Declaration.leg               == d['leg'],
                        Declaration.openDate          == asDate(d['openDate']),
                        Declaration.taReferenceActive == d['taReferenceActive'],
                        Declaration.pvReference       == d['pvReference'],
                        Declaration.taReference       == d['taReference'],
                        ).first()
                if not dd:
                    dd = Declaration(
                            term=term,
                            title_url=d['titleUrl'],
                            displayLanguageWarning =d['displayLanguageWarning'],
                            title=d['title'],
                            content=d['content'],
                            language=d['language'],
                            date=asDate(d['date']),
                            mep_id=mep.id,
                            pvReferenceActive = d['pvReferenceActive'],
                            pvReferenceUrl    = d['pvReferenceUrl'],
                            taReferenceUrl    = d['taReferenceUrl'],
                            expiryDate        = asDate(d['expiryDate']),
                            signatoryDate     = asDate(d['signatoryDate']),
                            nbSignatory       = d['nbSignatory'],
                            status            = d['status'],
                            leg               = d['leg'],
                            openDate          = asDate(d['openDate']),
                            taReferenceActive = d['taReferenceActive'],
                            pvReference       = d['pvReference'],
                            taReference       = d['taReference'],
                            )
                    session.add(dd)
                # add format list
                for f in d.get('formatList',[]):
                    ff = session.query(DeclarationFormat).filter(
                            DeclarationFormat.language == f['language'],
                            DeclarationFormat.title == f['title'],
                            DeclarationFormat.url == f['url'],
                            DeclarationFormat.pubRef == f['pubRef'],
                            DeclarationFormat.type == f['type'],
                            DeclarationFormat.size == f['size']
                            ).first()
                    if not ff:
                        ff = DeclarationFormat(
                                language=f['language'],
                                title=f['title'],
                                url=f['url'],
                                pubRef=f['pubRef'],
                                type=f['type'],
                                size=f['size'],
                                did=dd.id
                                )
                        session.add(ff)
                # committeelist
                for c in d.get('committeeList',[]):
                    name = c['title']
                    abbr = c['code']
                    cc = session.query(Committee).filter(Committee.name==name, abbr==abbr).first()
                    if not cc:
                        cc = Committee(name=name, abbr=abbr)
                        session.add(cc)
                        session.commit()
                    dd.committees.append(DeclarationCommittee(did=dd.id,com_id=cc.id))
                # referencelist (strings)
                for r in set(d.get('referenceList',[])):
                    rr = session.query(Reference).filter(Reference.reference==r).first()
                    if not rr:
                        rr = Reference(reference=r)
                        session.add(rr)
                        session.commit()
                    dd.references.append(DeclarationReference(did=dd.id,ref_id=rr.id))
        session.commit()

class Activity(Base):
    # TODO import in MEP.insert
    __tablename__ = 'activity'
    id = Column(Integer, primary_key=True)
    term = Column(Integer)
    type = Column(String(32))
    title_url = Column(String(512))
    displayLanguageWarning = Column(Boolean)
    title = Column(String(1024))
    text = Column(Text)
    content = Column(String(32)) # TODO seems to be always none, warn if not none!
    language = Column(String(2))
    date = Column(Date)
    shadow = Column(Boolean)
    # TODO referencelist (strings)
    mep_id = Column(Integer, ForeignKey(MEP.id))
    mep = relationship(
            MEP,
            foreign_keys="Activity.mep_id",
            backref=backref('activities', lazy='dynamic'),
            )


class ActivityFormat(Format):
    __tablename__ = "activity_format"
    aid = Column(Integer, ForeignKey(Activity.id))

    activity = relationship(
            Activity,
            foreign_keys="ActivityFormat.aid",
            backref=backref('formats', lazy='dynamic'),
            )


class ActivityCommittee(Base):
    __tablename__ = "activity_committee"
    aid = Column(Integer, ForeignKey(Activity.id), primary_key=True)
    com_id = Column(Integer, ForeignKey(Committee.id), primary_key=True)

    activity = relationship(
            Activity,
            foreign_keys="ActivityCommittee.aid",
            backref=backref('committees', lazy='dynamic'),
            )
    committee = relationship(
            Committee,
            foreign_keys="ActivityCommittee.com_id",
            backref=backref('activities', lazy='dynamic'),
            )


class Reference(Base):
    __tablename__ = "reference"
    id = Column(Integer, primary_key=True)
    reference = Column(String(32))


class ActivityReference(Base):
    __tablename__ = "activity_reference"
    aid = Column(Integer, ForeignKey(Activity.id), primary_key=True)
    ref_id = Column(Integer, ForeignKey(Reference.id), primary_key=True)

    activity = relationship(
            Activity,
            foreign_keys="ActivityReference.aid",
            backref=backref('references', lazy='dynamic'),
            )
    reference = relationship(
            Reference,
            foreign_keys="ActivityReference.ref_id",
            backref=backref('activities', lazy='dynamic'),
            )


class Declaration(Base): # in the dump this is marked as WDECL
    # TODO import in MEP.insert
    # TODO add authors
    __tablename__ = 'declarations'
    id = Column(Integer, primary_key=True)
    term = Column(Integer)
    pvReferenceActive = Column(Boolean)
    pvReferenceUrl = Column(String(512)) # always empty? TODO warn if not
    taReferenceUrl = Column(String(512)) # always empty? TODO warn if not
    title_url = Column(String(512)) 
    displayLanguageWarning = Column(Boolean)
    title = Column(String(1024))
    expiryDate = Column(Date)
    content = Column(String(32)) # TODO seems to be always none, warn if not none!
    signatoryDate = Column(Date)
    nbSignatory  = Column(Integer)
    status = Column(String(32))
    leg  = Column(Integer)
    language = Column(String(2))
    date = Column(Date)
    openDate = Column(Date)
    taReferenceActive = Column(Boolean)
    pvReference = Column(String(512)) # always empty? TODO warn if not
    taReference = Column(String(512)) # always empty? TODO warn if not
    # TODO referencelist (strings)
    mep_id = Column(Integer, ForeignKey(MEP.id))
    mep = relationship(
        MEP,
        foreign_keys="Declaration.mep_id",
        backref=backref('signed_declarations', lazy='dynamic'),
    )


class DeclarationFormat(Format):
    __tablename__ = "declaration_format"
    did = Column(Integer, ForeignKey(Declaration.id))

    declaration= relationship(
        Declaration,
        foreign_keys="DeclarationFormat.did",
        backref=backref('formats', lazy='dynamic'),
    )

class DeclarationAuthor(Base):
    __tablename__ = "declaration_author"
    did = Column(Integer, ForeignKey(Declaration.id), primary_key=True)
    mep_id = Column(Integer, ForeignKey(MEP.id), primary_key=True)

    declaration = relationship(
        Declaration,
        foreign_keys="DeclarationAuthor.did",
        backref=backref('authors', lazy='dynamic'),
    )
    mep = relationship(
        MEP,
        foreign_keys="DeclarationAuthor.mep_id",
        backref=backref('written_declarations', lazy='dynamic'),
    )

class DeclarationCommittee(Base):
    __tablename__ = "declaration_committee"
    did = Column(Integer, ForeignKey(Declaration.id), primary_key=True)
    com_id = Column(Integer, ForeignKey(Committee.id), primary_key=True)

    declaration = relationship(
        Declaration,
        foreign_keys="DeclarationCommittee.did",
        backref=backref('committees', lazy='dynamic'),
    )
    committee = relationship(
        Committee,
        foreign_keys="DeclarationCommittee.com_id",
        backref=backref('written_declarations', lazy='dynamic'),
    )


class DeclarationReference(Base):
    __tablename__ = "declaration_reference"
    did = Column(Integer, ForeignKey(Declaration.id), primary_key=True)
    ref_id = Column(Integer, ForeignKey(Reference.id), primary_key=True)

    declaration = relationship(
            Declaration,
            foreign_keys="DeclarationReference.did",
            backref=backref('references', lazy='dynamic'),
            )
    reference = relationship(
            Reference,
            foreign_keys="DeclarationReference.ref_id",
            backref=backref('declarations', lazy='dynamic'),
            )


class PartDecl(Base):
    __tablename__ = 'partdecl'

    id = Column(Integer, primary_key=True)
    url = Column(String(512), unique=True)
    mep_id = Column(Integer, ForeignKey(MEP.id))
    mep = relationship(
        MEP,
        foreign_keys="PartDecl.mep_id",
        backref=backref('partdecls', lazy='dynamic'),
    )


class Office(Base):
    """ An office of a MEP"""
    __tablename__ = 'office'

    id = Column(Integer, primary_key=True)
    floor = Column(String(255))
    office_number = Column(String(255))
    fax = Column(String(255))
    phone1 = Column(String(255))
    phone2 = Column(String(255))
    building_id = Column(Integer, ForeignKey(Building.id))
    building = relationship(
        Building,
        foreign_keys="Office.building_id",
        backref=backref('offices', lazy='dynamic'),
    )
    mep_id = Column(Integer, ForeignKey(MEP.id))
    mep = relationship(
        MEP,
        foreign_keys="Office.mep_id",
        backref=backref('offices', lazy='dynamic'),
    )


    def __unicode__(self):
        return u"%s - %s - %s - %s" % (self.id, self.building.__unicode__(), self.floor, self.office_number)

    def __repr__(self):
        return u"%s - %s - %s" % (self.building.__repr__(), self.floor, self.office_number)

    @staticmethod
    def get_by_id(id):
        # TODO
        return

    @staticmethod
    def upsert(data):
        # TODO
        return

    @staticmethod
    def load(data):
        # TODO
        return


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
        return u"%s %s [%s]" % (self.mep.first_name, self.mep.last_name, self.group.abbr)


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
        return u"%s : %s" % (self.committee.abbr, self.mep.full_name)


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
        return u"%s : %s" % (self.committee.abbr, self.mep.full_name)


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
    name = Column(String(255))

    def __unicode__(self):
        return self.name


class AssistantMEP(Base):
    __tablename__ = 'assistant_mep'

    id = Column(Integer, primary_key=True)
    mep_id = Column(Integer, ForeignKey(MEP.id))
    assistant_id = Column(Integer, ForeignKey(Assistant.id))
    type = Column(String(255))
    mep = relationship(
        MEP,
        foreign_keys="AssistantMEP.mep_id",
        backref=backref('assistants', lazy='dynamic'),
    )
    assistant = relationship(
        Assistant,
        foreign_keys="AssistantMEP.assistant_id",
        backref=backref('meps', lazy='dynamic'),
    )


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

    amendment_id = Column(Integer, ForeignKey(Amendment.id), primary_key=True)
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
