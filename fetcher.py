import sys
import os
import numpy as np
import pandas as pd
import warnings
from abc import abstractmethod
from io_utils import read_textfile
from parser import Parser, nonempty_segments
from blob import get_block_constructor, Block, Atom, get_blank
from global_utils import capitalize
from data import AtomicData
from collections import Counter, defaultdict


class Fetcher:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.cache = {}

    @abstractmethod
    def fetch(self, *args, **kwargs):
        pass

    def clear_cache(self):
        self.cache = {}


class FlockFetcher(Fetcher):
    def __init__(self, root_dir):
        super(FlockFetcher, self).__init__(root_dir=root_dir)
        self.mutex_counters = defaultdict(Counter)

    def clear_cache(self):
        super(FlockFetcher, self).clear_cache()
        self.mutex_counters = defaultdict(Counter)

    def sample(self, col, cls, mutex=None):
        fpath = os.path.join(self.root_dir, col, cls + ".txt")
        if fpath in self.cache:
            possibilities = self.cache[fpath]
        else:
            text = read_textfile(fpath)
            possibilities = {poss.strip() for poss in text.split('\n') if len(poss.strip()) != 0}
            self.cache[fpath] = possibilities

        if not mutex:
            return np.random.choice(list(possibilities))

        counter = self.mutex_counters[(mutex, col, cls)]

        if list(counter.elements()):
            assert max(counter.values()) - min(counter.values()) <= 1
            _, most_used_value = counter.most_common(n=1)[0]
            most_used_keys = {k for k, v in counter.items() if v == most_used_value}
        else:
            most_used_keys = set()

        new_possibilities = possibilities - most_used_keys
        print(f'Using mutex = {mutex}, {len(new_possibilities)}/{len(possibilities)} available '
              f'for {col.capitalize()}-{cls.capitalize()}')
        if not new_possibilities:
            print(f'Warning: choices drained for mutex == {mutex}, col == {col}, cls == {cls}, ')
            new_possibilities = possibilities

        choice = np.random.choice(list(new_possibilities))
        counter[choice] += 1

        return choice

    def fetch(self, tag, col, cls, sample_type='paragraph', wrap_with="block", mutex=None):
        sample = self.sample(col, cls, mutex)
        parser = Parser()
        parsed_samples = [parser.parse(sample, ret_type=sample_type)]
        block_constructor = get_block_constructor(wrap_with)
        return {tag: block_constructor(parsed_samples, atomic=False)}


class ProjectInfoFetcher(Fetcher):
    def __init__(self, root_dir, description_path=None, signature_path=None, date_path=None, program_name_path=None):
        super(ProjectInfoFetcher, self).__init__(root_dir=root_dir)
        if description_path is None:
            description_path = "program_description.txt"
        if signature_path is None:
            signature_path = "instructor_signature.txt"
        if date_path is None:
            date_path = "date.txt"
        if program_name_path is None:
            program_name_path = "program_name.txt"

        self.description_path = os.path.join(root_dir, description_path)
        self.signature_path = os.path.join(root_dir, signature_path)
        self.date_path = os.path.join(root_dir, date_path)
        self.program_name_path = os.path.join(root_dir, program_name_path)

    def sample_from_cache(self):
        ret = {}
        for k in self.cache:
            v = self.cache[k]
            if isinstance(v, (list, tuple)):
                v = np.random.choice(v)
            ret[k] = v
        return ret

    def fetch(self, verbatim=False):
        if len(self.cache) == 0:
            self.set_cache(verbatim=verbatim)
        return self.sample_from_cache()

    def set_cache(self, verbatim=True):
        description = read_textfile(self.description_path)
        signature = read_textfile(self.signature_path)
        date = nonempty_segments(read_textfile(self.date_path), "\n")
        program_name = read_textfile(self.program_name_path)

        if verbatim:
            description = Atom(description)
            signature = Atom(signature)
            date = [Atom(d) for d in date]
            program_name = Atom(program_name)
        else:
            parser = Parser()
            description = parser.parse_paragraph(description)
            signature = Block(
                [parser.parse_sentence(line) for line in signature.split("\n")],
                atomic=False, separator="\n",
            )
            date = [parser.parse_sentence(d) for d in date]
            program_name = parser.parse_sentence(program_name)

        self.cache = {
            "program_description": description,
            "instructor_signature": signature,
            "date": date,
            "program_name": program_name,
        }


class StudentFetcher(Fetcher):
    def __init__(self, root_dir, name_list_path, flock_fetcher):
        super(StudentFetcher, self).__init__(root_dir=root_dir)
        if name_list_path is None:
            name_list_path = "name_list.txt"

        self.name_list_path = os.path.join(self.root_dir, name_list_path)
        self.cache = None
        self.basic_columns = [
            'first_name',
            'last_name',
            'gender',
            'assignment',
            'participation',
            'final',
            'overall',
        ]
        self.additional_columns = []
        self.flock_fetcher = flock_fetcher  # type: FlockFetcher

    def set_cache(self):
        if not os.path.isfile(self.name_list_path):
            raise FileNotFoundError(f"{self.name_list_path} is not a file")
        try:
            self.cache = pd.read_csv(self.name_list_path)
        except UnicodeDecodeError as e:
            raise ValueError(f"Unrecognized-encoding format; please encode the csv file in UTF-8 "
                             f"(default encoding on macOS and Linux)."
                             f"\nFor windows users, please paste to Google Sheet and download a CSV from there."
                             f"\n{e}")

        for col in self.basic_columns:
            if col not in self.cache.columns:
                raise ValueError(f"'{col}' not found in {self.name_list_path}; "
                                 f"check these table header again: \n {self.cache.columns}")
            self._preprocess_column(col)

        self.additional_columns = [col for col in self.cache.columns if col not in self.basic_columns]
        self.check_rows()

    def clear_cache(self):
        self.cache = None

    def _preprocess_column(self, col_name):
        self.cache[col_name] = self.cache[col_name].apply(lambda g: capitalize(g.strip()))

    def check_rows(self):
        for i, row in self.cache.iterrows():
            if row['gender'] not in ['M', 'F']:
                raise ValueError(f"Unknown gender {row} for {row['first_name']} {row['last_name']} found")
            for col in ['assignment', 'participation', 'final', 'overall']:
                if row[col] not in ['A', 'B', 'C', 'D']:
                    raise ValueError(f"Unknown {col} grade '{row[col]}' for {row['first_name']} {row['last_name']}")

    def fetch_flock(self, row, col, type='sentence'):
        if type == 'sentence':
            prefix = 'sent'
        elif type == 'paragraph':
            prefix = 'para'
        else:
            raise ValueError(f"Unrecognized type = {type}")
        mutex = row.get('mutex')
        if mutex:
            mutex = str(mutex).strip()

        return self.flock_fetcher.fetch(tag=f'{prefix}_{col}', col=col, cls=row[col].lower(), wrap_with='paragraph',
                                        mutex=mutex)

    def fetch_row(self, row):
        d = {
            'first_name': Atom(row['first_name']),
            'last_name': Atom(row['last_name']),
            'he': Atom('he' if row['gender'] == "M" else 'she'),
            'him': Atom('him' if row['gender'] == "M" else 'her'),
            'his': Atom('his' if row['gender'] == "M" else 'her'),
            'himself': Atom('himself' if row['gender'] == "M" else 'herself'),
            'He': Atom('He' if row['gender'] == "M" else 'She'),
            'Him': Atom('Him' if row['gender'] == "M" else 'Her'),
            'His': Atom('His' if row['gender'] == "M" else 'Her'),
            'Himself': Atom('Himself' if row['gender'] == "M" else 'Herself'),
        }

        for col in ['participation', 'overall', 'assignment', 'final']:
            slot_data = self.fetch_flock(row, col, type='sentence')
            for k in slot_data:
                slot_data[k].fill_(d)
            d.update(slot_data)

        parser = Parser()
        for col in self.additional_columns:
            slot_data = parser.parse_by_tag(col, str(row[col]))
            for k in slot_data:
                slot_data[k].fill_(d)
            d.update(slot_data)

        return d

    def fetch(self):
        if self.cache is None:
            self.set_cache()

        return [self.fetch_row(row) for i, row in self.cache.iterrows()]


class GenreFormer:
    def __init__(self, root_dir, genre_path=None):
        self.root_dir = root_dir
        if genre_path is None:
            genre_path = "genre.txt"
        self.genre_path = os.path.join(self.root_dir, genre_path)

    def get_genre(self):
        genre = read_textfile(self.genre_path)
        parser = Parser()
        genre = parser.parse_article(genre)
        return genre
