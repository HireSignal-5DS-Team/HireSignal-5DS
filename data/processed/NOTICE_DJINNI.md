# Notice: Djinni Recruitment Dataset (MIT)

The files in `data/processed/cvs/` and `data/processed/jobs/` are copies of records from the Djinni Recruitment
Dataset, English part:

- CVs: https://huggingface.co/datasets/lang-uk/recruitment-dataset-candidate-profiles-english (revision `86255174c6c378a2b52cd7e81d79002c64d899a6`)
- Jobs: https://huggingface.co/datasets/lang-uk/recruitment-dataset-job-descriptions-english (revision `b56a6054c10f1266a141e37c8df66c79ff2863af`)
- Project: https://github.com/Stereotypes-in-LLMs/recruitment-dataset

Both dataset cards declare `license: mit` (checked 2026-10-18). The cards give no copyright line; the holder below is
the dataset authors as named in the paper. (The GitHub project repository itself carries an Apache-2.0 licence for
its code; the data we copied comes from the Hugging Face datasets above.)

Our changes: CRLF -> LF, one header block per CV (Position, Experience years, English level from the same record),
only 40 CVs and 4 jobs selected (`scripts/build_labelling_kit.py`). The text is otherwise unchanged.

## Citation

```bibtex
@inproceedings{drushchak-romanyshyn-2024-introducing,
    title = "Introducing the Djinni Recruitment Dataset: A Corpus of Anonymized {CV}s and Job Postings",
    author = "Drushchak, Nazarii  and Romanyshyn, Mariana",
    booktitle = "Proceedings of the Third Ukrainian Natural Language Processing Workshop (UNLP) @ LREC-COLING 2024",
    month = may,
    year = "2024",
    address = "Torino, Italia",
    publisher = "ELRA and ICCL",
    url = "https://aclanthology.org/2024.unlp-1.2",
    pages = "8--13",
}
```

## MIT License

Copyright (c) 2024 Nazarii Drushchak, Mariana Romanyshyn (Djinni Recruitment Dataset authors)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
