#!/usr/bin/env python

import string
from nltk.corpus import stopwords
import textdistance

def clean_string(txt):
    txt = ''.join([word for word in txt if word not in string.punctuation])
    txt = txt.lower()
    txt = ' '.join([word for word in txt.split() if word not in stopwords])
    return txt

stopwords=stopwords.words('english')
print(
    textdistance.Cosine(qval=1).normalized_similarity(*list(map(clean_string, ["2021 discharge: General budget of the EU - European Commission", "2021 discharge: General budget of the EU - Commission"])))
    )
