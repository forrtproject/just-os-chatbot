#!/bin/sh
# Answer one glossary item file in full with and without the library, then judge both runs.
# Usage (in the web container): sh eval/answer_items.sh <generator>, e.g. openai__gpt-4.1-mini
# Output: eval/results/glossary_<generator>_library.csv and _noretrieval.csv
set -e
g=$1
items=eval/glossary_items_$g.jsonl
python eval/run.py --model meta-llama/llama-3.1-8b-instruct --questions "$items" --skip-classifier \
  --full-answers --out "eval/results/glossary_${g}_library.csv"
python eval/run.py --model meta-llama/llama-3.1-8b-instruct --questions "$items" --no-retrieval \
  --full-answers --out "eval/results/glossary_${g}_noretrieval.csv"
for mode in library noretrieval; do
  python eval/rubric_judge.py "eval/results/glossary_${g}_${mode}.csv" --items "$items"
done
