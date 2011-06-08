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

def diff(e1,e2, path=[]):
    if not e1 and e2:
        return [{'added': e2, 'path': path}]
    elif not e2 and e1:
        return [{'deleted': e1, 'path': path}]
    if type(e1) == str: e1=unicode(e1,'utf8')
    if type(e2) == str: e2=unicode(e2,'utf8')
    if not type(e1)==type(e2):
        return [{'changed': (e1, e2), 'path': path}]
    elif hasattr(e1,'keys'):
        res=[]
        for k in set(e1.keys() + (e2 or {}).keys()):
            r=diff(e1.get(k),(e2 or {}).get(k), path+[k])
            if r:
                res.extend(r)
        return res
    elif hasattr(e1,'__iter__'):
        res=[]
        for item in filter(None,[diff(a,b,path+[i]) for i,(a,b) in enumerate(izip_longest(e1,(e2 or [])))]):
            if type(item)==type(list()):
                res.extend(item)
            else:
                append(item)
        return res
    elif e1 != e2:
        return [{'changed': (e1, e2), 'path': path}]
    return

def test_diff():
    d2={ 'a': [ { 'aa': 1, 'bb':2 }, {'AA': 1, 'BB': { 'asdf': 'qwer'} } ],
         'c': [ 1,2,3,4]}
    d1={ 'a': [ { 'aa': 1, 'bb':3 }, {'AA': 1, 'BB': { 'asdf': { 'asdf': 'qwer'}}}, {'Mm': [ 'a','b','c','d'] } ],
         'b': { 'z': 9, 'x': 8 },
         'c': [ 3,4,5,9,10]}
    import pprint
    pprint.pprint(diff(d1,d2))

if __name__ == "__main__":
    test_diff()
