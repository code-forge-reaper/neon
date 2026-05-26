test: tokenizer.py
	python neon2c dump ast test.neon

tokenizer.py: tokeniser.rdb
	python extract.py
