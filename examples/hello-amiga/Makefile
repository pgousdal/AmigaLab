CC := m68k-amigaos-gcc
CFLAGS := -Os -Wall -Wextra -noixemul
BUILD_DIR := build
TARGET := $(BUILD_DIR)/hello-amiga
SOURCE := src/main.c

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SOURCE)
	mkdir -p $(BUILD_DIR)
	$(CC) $(CFLAGS) -o $@ $<

clean:
	rm -rf $(BUILD_DIR)
