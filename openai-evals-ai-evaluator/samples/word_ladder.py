def word_ladder(start_word: str, end_word: str, word_list: list) -> list:
    """Find shortest transformation sequence from start_word to end_word using words from word_list.
    Returns the transformation sequence as a list of words, or empty list if no sequence exists."""
    if start_word == end_word:
        return [start_word]

    word_set = set(word_list)
    queue = [(start_word, [start_word])]
    seen = {start_word}

    while queue:
        current_word, path = queue.pop(0)

        # Try changing each character position
        for i in range(len(current_word)):
            # Try all possible letters
            for c in 'abcdefghijklmnopqrstuvwxyz':
                next_word = current_word[:i] + c + current_word[i+1:]

                if next_word == end_word and next_word in word_set:
                    return path + [next_word]

                if next_word in word_set and next_word not in seen:
                    seen.add(next_word)
                    queue.append((next_word, path + [next_word]))

    return []
