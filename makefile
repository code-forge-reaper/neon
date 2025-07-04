test: tokenizer.py
	# generate AST
	python neon.py test.neon
	
	# generate C
	python generate.py test.neon

tokenizer.py: tokeniser.rdb
	python extract.py
