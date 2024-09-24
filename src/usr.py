import re
from unicodedata import normalize


def slugify(text, delim="-"):
    """Generates a slightly worse ASCII-only slug."""

    _punct_re = re.compile(r'[\t !"#$%&\'()*\-/<=>?@\[\\\]^_`{|},.:]+')
    _regex = re.compile("[^a-z0-9]")
    # The First parameter is the replacement, the second parameter is your input string

    result = []
    for word in _punct_re.split(text.lower()):
        word = normalize("NFKD", word).encode("ascii", "ignore")  # noqa PLW2901
        word = word.decode("ascii")  # noqa PLW2901
        word = _regex.sub("", word)  # noqa PLW2901
        if word:
            result.append(word)
    slug = delim.join(result)
    return str(slug)
