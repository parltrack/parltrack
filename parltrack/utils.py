from BeautifulSoup import BeautifulSoup, Comment
from itertools import izip_longest

def sanitizeHtml(value, base_url=None):
    rjs = r'[\s]*(&#x.{1,7})?'.join(list('javascript:'))
    rvb = r'[\s]*(&#x.{1,7})?'.join(list('vbscript:'))
    re_scripts = re.compile('(%s)|(%s)' % (rjs, rvb), re.IGNORECASE)
    validTags = 'p i strong b u a h1 h2 h3 pre br img'.split()
    validAttrs = 'href src width height'.split()
    urlAttrs = 'href src'.split() # Attributes which should have a URL
    soup = BeautifulSoup(value)
    for comment in soup.findAll(text=lambda text: isinstance(text, Comment)):
        # Get rid of comments
        comment.extract()
    for tag in soup.findAll(True):
        if tag.name not in validTags:
            tag.hidden = True
        attrs = tag.attrs
        tag.attrs = []
        for attr, val in attrs:
            if attr in validAttrs:
                val = re_scripts.sub('', val) # Remove scripts (vbs & js)
                if attr in urlAttrs:
                    val = urljoin(base_url, val) # Calculate the absolute url
                tag.attrs.append((attr, val))

    return soup.renderContents().decode('utf8')

def diff(old, new, path=[]):
    if old==None and new!=None:
        return [{'type': 'added', 'data': new, 'path': path}]
    elif new==None and old!=None:
        return [{'type': 'deleted', 'data': old, 'path': path}]
    if type(old) == str: old=unicode(old,'utf8')
    if type(new) == str: new=unicode(new,'utf8')
    if not type(old)==type(new):
        return [{'type': 'changed', 'data': (old, new), 'path': path}]
    elif hasattr(old,'keys'):
        res=[]
        for k in set(old.keys() + (new or {}).keys()):
            r=diff(old.get(k),(new or {}).get(k), path+[k])
            if r:
                res.extend(r)
        return res
    elif hasattr(old,'__iter__'):
        res=[]
        for item in filter(None,[diff(a,b,path+[(len(old) if len(old)<len(new) else len(new))-i]) for i,(a,b) in enumerate(izip_longest(reversed(old),reversed(new)))]):
            if type(item)==type(list()):
                res.extend(item)
            else:
                res.append(item)
        return res
    elif old != new:
        return [{'type': 'changed', 'data': (old, new), 'path': path}]
    return

def test_diff():
    d2={ 'a': [ {'aa': 2, 'bb': 3 }, { 'aa': 1, 'bb':3 }, {'AA': 1, 'BB': { 'asdf': { 'asdf': 'qwer'}}}, {'Mm': [ 'a','b','c','d'] } ],
         'c': [ 0,1,2,3,4]}
    d1={ 'a': [ { 'aa': 1, 'bb':3 }, {'AA': 1, 'BB': { 'asdf': '2'}}, {'Mm': [ 'a','b','c','d'] } ],
         'b': { 'z': 9, 'x': 8 },
         'c': [ 1,2,3,4]}
    import pprint
    pprint.pprint(diff(d1,d2))

if __name__ == "__main__":
    test_diff()

def dateJSONhandler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    elif type(obj)==ObjectId:
        return str(obj)
    else:
        raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj))
