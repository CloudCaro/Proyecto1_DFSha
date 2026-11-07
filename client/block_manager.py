import hashlib


BLOCK_SIZE = 4 * 1024 * 1024


class BlockManager:

    @staticmethod
    def calculate_hash(content):

        return hashlib.sha256(
            content
        ).hexdigest()

    @staticmethod
    def split_file(content):

        blocks = []

        for index in range(
            0,
            len(content),
            BLOCK_SIZE
        ):

            block = content[
                index:index + BLOCK_SIZE
            ]

            blocks.append({
                "content": block,
                "size": len(block),
                "sha256": BlockManager.calculate_hash(
                    block
                )
            })

        return blocks

    @staticmethod
    def get_file_hash(content):

        return BlockManager.calculate_hash(
            content
        )