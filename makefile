test:test.neon
	python neon2c emit c test.neon -o test.c
	cc test.c -o test
