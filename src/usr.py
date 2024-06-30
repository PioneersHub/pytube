import re
from unicodedata import normalize

def slugify(text, delim="-"):
    """Generates a slightly worse ASCII-only slug."""

    _punct_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|},.:]+')
    _regex = re.compile("[^a-z0-9]")
    # First parameter is the replacement, second parameter is your input string

    result = []
    for word in _punct_re.split(text.lower()):
        word = normalize("NFKD", word).encode("ascii", "ignore")
        word = word.decode("ascii")
        word = _regex.sub("", word)
        if word:
            result.append(word)
    slug = delim.join(result)
    return str(slug)