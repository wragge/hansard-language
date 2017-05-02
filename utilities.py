import os
import re
from sklearn.feature_extraction.text import TfidfVectorizer


def generate_tfidf(data_dir, ngram):
    results = []
    # Get a list of the reasons from the file titles
    names = [file[:-4] for file in os.listdir(data_dir) if file[-4:] == '.txt']
    # Get a list of filenames to feed to scikit-learn
    files = [os.path.join(data_dir, file) for file in os.listdir(data_dir) if file[-4:] == '.txt']
    # Chomp chomp -- getting trigrams
    tf = TfidfVectorizer(input='filename', analyzer='word', ngram_range=(ngram, ngram), min_df=0, stop_words='english', smooth_idf=False, sublinear_tf=True)
    tfidf_matrix = tf.fit_transform(files)
    # These are the actual phrases
    feature_names = tf.get_feature_names()
    # These are the scores
    reasons = tfidf_matrix.todense()
    for index, row in enumerate(reasons):
        name = names[index]
        print '\n\n{}\n'.format(name.upper())
        reason = row.tolist()[0]
        # If the score is not 0 save it with an index (which will let us get the feature_name)
        scores = [pair for pair in zip(range(0, len(reason)), reason) if pair[1] > 0]
        sorted_scores = sorted(scores, key=lambda t: t[1] * -1)
        # Get labelled score, reomoving numbers
        labelled_scores = [(feature_names[word_id], score) for (word_id, score) in sorted_scores if not re.search(r'^\d+$', feature_names[word_id])]
        # score_dict = dict(labelled_scores[:200])
        # Print the top 10 results
        for phrase, score in labelled_scores[:20]:
            print('{0: <40} {1}'.format(phrase.encode('utf-8'), score))
        results.append({'name': name, 'scores': labelled_scores[:200]})
    return results
