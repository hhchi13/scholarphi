"""


"""

from typing import *

import json
import os
from tqdm import tqdm
import csv

from common.bounding_box import BoundingBox
from collections import defaultdict

import numpy as np
from functools import cmp_to_key

from argparse import ArgumentParser

from entities.sentences import upload
from common.types import EntityUploadInfo
from common.models import init_database_connections

import spacy
nlp = spacy.load("en_core_sci_md")


def bbox_to_json(bbox: BoundingBox) -> List:
    return [bbox.left, bbox.top, bbox.width, bbox.height, bbox.page]

class SppBbox:
    def __init__(self, left: float, top: float, right: float, bottom: float, page_id: int):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom
        self.page_id = page_id


class TokenWithBBox:
    def __init__(self, text: str, bbox: BoundingBox):
        self.text = text
        self.bbox = bbox

    def __str__(self):
        return f"{self.text}    (left={self.bbox.left:.3f}, top={self.bbox.top:.3f}, width={self.bbox.width:.3f}, height={self.bbox.height:.3f}, page={self.bbox.page})"

    def __repr__(self):
        return self.__str__()

    def to_json(self) -> Dict:
        return {
            'text': self.text,
            'bbox': bbox_to_json(bbox=self.bbox)
        }


class SentenceWithBbox:
    def __init__(self, text: str, bboxes: List[BoundingBox]):
        self.text = text
        self.bboxes = bboxes

    def __str__(self):
        s = ''
        for bbox in self.bboxes:
            s += f"    (left={bbox.left:.2f}, top={bbox.top:.2f}, width={bbox.width:.2f}, height={bbox.height:.2f}, page={bbox.page})\n"
        return f"text={self.text}\n{s}"

    def __repr__(self):
        return self.__str__()

    def to_json(self) -> Dict:
        return {
            'text': self.text,
            'bboxes': [bbox_to_json(bbox=bbox) for bbox in self.bboxes]
        }


class Block:
    def __init__(self, tokens: List[TokenWithBBox], bbox: BoundingBox, type: str):
        self.tokens = tokens
        self.bbox = bbox
        self.type = type

        # 1) compute what the entire text block looks like & use it to represent tokens & sentences in a shared char index space
        self.text: str = ' '.join([t.text for t in self.tokens])
        self.token_char_spans: List[Tuple] = self._compute_token_char_spans()       # O(num_tokens)
        self.sent_char_spans: List[Tuple] = self._compute_sent_char_spans()         # O(num_sents)

        # 2) use these spans to align tokens to sentences
        #       [[0, 1, 2], [3, 4, 5], ...] means the first 3 tokens (0, 1, 2) belong in sentence 0, next 3 in sentence 1, etc.
        self.token_sent_clusters: List[List[int]] = self._cluster_tokens_by_sents()

        # 3) cluster tokens into rows
        #       [[0, 1, 2], [3, 4, 5], ...] means the first 3 tokens (0, 1, 2) belong in row 0, next 3 in row 1, etc.
        self.token_row_clusters: List[List[int]] = self._cluster_tokens_by_row()

        # 4) using the rows, compute bboxes for sentences
        self.sents: List[SentenceWithBbox] = self._build_sentences()

    def __str__(self):
        ss = '\n'.join([str(s) for s in self.sents])
        return f"**type={self.type}**\n\n{ss}"

    def __repr__(self):
        return self.__str__()

    def to_json(self) -> Dict:
        return {
            'text': self.text,
            'type': self.type,
            'tokens': [token.to_json() for token in self.tokens],
            'sents': [sent.to_json() for sent in self.sents],
        }

    #
    #   Methods for step (1)
    #

    def _compute_sent_char_spans(self) -> List[Tuple]:
        sent_char_spans = []
        start = 0
        doc = nlp(self.text)
        for i in range(1, len(doc)):
            if doc[i].is_sent_start:
                end = doc[i - 1].idx + len(doc[i - 1].text)
                sent_char_spans.append((start, end))
                start = doc[i].idx
        # handle ending
        sent_char_spans.append((start, len(self.text)))
        return sent_char_spans

    def _compute_token_char_spans(self) -> List[Tuple]:
        # TODO; this only works because all tokens are whitespace delim  (hence start = end + 1)
        token_char_spans = []
        start = 0
        for t in self.tokens:
            end = start + len(t.text)
            token_char_spans.append((start, end))
            start = end + 1
        return token_char_spans

    #
    #   Methods for step (2)
    #

    def _find_sent_idx_for_this_token_char_span(self, token_start: int, token_end: int) -> int:
        # quantifies how much of token "sticks out" of the sentence boundary, for each sentence
        leftovers_per_sent = []
        for sent_start, sent_end in self.sent_char_spans:
            # penalize case where token start is left of sent start
            start_leftover = max(sent_start - token_start, 0)
            # penalize case where token end is right of sent end
            end_leftover = max(token_end - sent_end, 0)
            leftovers_per_sent.append(start_leftover + end_leftover)

        # find best matching sentence for this token
        idx_best_sent = np.argmin(leftovers_per_sent)
        return int(idx_best_sent)

    def _cluster_tokens_by_sents(self) -> List[List[int]]:
        sent_clustered_token_idx = [[] for _ in range(len(self.sent_char_spans))]
        for token_idx, (token_start, token_end) in enumerate(self.token_char_spans):
            sent_idx = self._find_sent_idx_for_this_token_char_span(token_start=token_start, token_end=token_end)
            sent_clustered_token_idx[sent_idx].append(token_idx)
        return sent_clustered_token_idx

    #
    #   Methods for step (3)
    #

    # TODO: ther'es probably a better way to solve this clustering problem as an optim problem.
    #       for example, dbscan or k-means w/ distance metric based on y-coord
    def _cluster_tokens_by_row(self) -> List[List[int]]:
        # cluster incrementally O(num_tokens)
        clusters = [[0]]
        for token_idx in range(1, len(self.tokens)):
            current_token = self.tokens[token_idx]
            prev_token = self.tokens[token_idx - 1]
            if _are_same_row(bbox1=prev_token.bbox, bbox2=current_token.bbox):
                clusters[-1].append(token_idx)
            else:
                clusters.append([token_idx])
        return clusters

    #
    #   Methods for step (4)
    #

    def _compute_sent_bboxes(self, token_sent_cluster: List[int]) -> List[BoundingBox]:
        """
        For input, you provide all the tokens belonging to this sentence.

        In this method, we keep the tokens clustered by rows, but only consider tokens that are in this sentence.
        This allows us to compute a bounding box for this row (or sub-row) to associate w/ this sentence.

        The sentence bboxes overall are then composed of all the disjoint bounding boxes for each row (or sub-row).
        """
        sent_bboxes = []
        for token_row_cluster in self.token_row_clusters:
            tokens_in_this_row_and_this_sent = [token_idx for token_idx in token_row_cluster if token_idx in token_sent_cluster]
            if tokens_in_this_row_and_this_sent:
                unioned_bbox = _union_bboxes(bboxes=[self.tokens[i].bbox for i in tokens_in_this_row_and_this_sent])
                sent_bboxes.append(unioned_bbox)
        return sent_bboxes

    def _build_sentences(self) -> List[SentenceWithBbox]:
        sents = []
        for token_sent_cluster, (sent_start, sent_end) in zip(self.token_sent_clusters, self.sent_char_spans):
            sent_bboxes = self._compute_sent_bboxes(token_sent_cluster=token_sent_cluster)
            sent = SentenceWithBbox(text=self.text[sent_start:sent_end], bboxes=sent_bboxes)
            sents.append(sent)
        return sents


def normalize_spp_bbox_json(spp_bbox_json: Dict, page_id: int, spp_page_height: float, spp_page_width: float) -> BoundingBox:
    left, top, right, bottom = spp_bbox_json
    spp_bbox = SppBbox(left=left, top=top, right=right, bottom=bottom, page_id=page_id)
    return BoundingBox(left=spp_bbox.left / spp_page_width,
                       top=spp_bbox.top / spp_page_height,
                       width=(spp_bbox.right - spp_bbox.left) / spp_page_width,
                       height=(spp_bbox.bottom - spp_bbox.top) / spp_page_height,
                       page=spp_bbox.page_id)


def _are_same_row(bbox1: BoundingBox, bbox2: BoundingBox) -> bool:
    """Taken from https://github.com/allenai/scholarphi/blob/381eea6cf540fdc130fc10f032b883fa0ef64af4/data-processing/pdf/process_pdf.py#L61"""
    return bbox1.page == bbox2.page and (
        abs(bbox1.top - bbox2.top) < 0.01  # Same y-coordinate
    ) #and (
        # abs(bbox2.left - bbox1.left - bbox1.width) < 0.05     # To the right
    # )


def _union_bboxes(bboxes: List[BoundingBox]) -> BoundingBox:
    """Taken from https://github.com/allenai/scholarphi/blob/381eea6cf540fdc130fc10f032b883fa0ef64af4/data-processing/pdf/process_pdf.py#L48"""
    assert len({bbox.page for bbox in bboxes}) == 1
    x1 = min([bbox.left for bbox in bboxes])
    y1 = min([bbox.top for bbox in bboxes])
    x2 = max([bbox.left + bbox.width for bbox in bboxes])
    y2 = max([bbox.top + bbox.height for bbox in bboxes])
    return BoundingBox(page=bboxes[0].page, left=x1, top=y1, width=x2 - x1, height=y2 - y1)


def process_page_for_blocks(page_dict: Dict) -> List[Block]:
    page_height = page_dict['height']
    page_width = page_dict['width']
    page_id = page_dict['index']
    block_dicts = page_dict['layout']['bundles']  # wtf are remaining_tokens?

    blocks: List[Block] = []
    for block_dict in block_dicts:
        block_bbox: BoundingBox = normalize_spp_bbox_json(spp_bbox_json=block_dict['bbox'],
                                                          page_id=page_id,
                                                          spp_page_height=page_height,
                                                          spp_page_width=page_width)
        block_tokens: List[TokenWithBBox] = [
            TokenWithBBox(text=token_dict['text'],
                          bbox=normalize_spp_bbox_json(spp_bbox_json=token_dict['bbox'],
                                                       page_id=page_id,
                                                       spp_page_height=page_height,
                                                       spp_page_width=page_width))
            for token_dict in block_dict['tokens']
        ]
        block = Block(tokens=block_tokens, bbox=block_bbox, type=block_dict['type'])
        blocks.append(block)

    # TODO: blocks are currently out of reading order.  maybe do some processing here.

    return blocks


# def sort_blocks(blocks: List[Block]) -> List[Block]:
#     sorted_blocks = sorted(
#         blocks, key=cmp_to_key(lambda x, y: 1 if block.bbox.page < block.bbox.page else (
#             1 if block.bbox.left < block.bbox.left else (
#                 1 if block.bbox.
#             )
#         ))
#     )


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("--infile", help="Path to input Scienceparse+ JSON", required=True, type=str)
    parser.add_argument("--outfile", help="Path to output JSON file", required=True, type=str)
    parser.add_argument("--outdir", help="Path to output bunch of CSV files for uploading", type=str)
    args = parser.parse_args()

    with open(args.infile) as f_in:
        page_dicts = json.load(f_in)
        blocks: List[Block] = []
        for page_dict in tqdm(page_dicts):
            blocks.extend(process_page_for_blocks(page_dict=page_dict))



    with open(args.outfile, 'w') as f_out:
        out = []
        for block in blocks:
            if block.type in {'figure', 'table'}:
                continue
            out.append(block.to_json())
            del out[-1]['tokens']
        json.dump(out, f_out, indent=4)

    # init database
    init_database_connections(schema_name='kyle_spp', create_tables=True)

    # upload entities
    entity_infos = []
    for block_idx, block in enumerate(blocks):
        for sent_idx, sent in enumerate(block.sents):
            entity_info = EntityUploadInfo(
                id_=f"{block_idx}-{sent_idx}",
                type_="sentence",
                bounding_boxes=sent.bboxes,
                data={
                    "text": sent.text,
                    "tex": 'NO_LATEX',
                    "tex_start": -1,
                    "tex_end": -1,
                },
            )
            entity_infos.append(entity_info)
    upload.upload_entities(s2_id='9c5c794094fbf5da8c48df5c3242615dc0b1d245',
                           arxiv_id='1811.12359',
                           entities=entity_infos,
                           data_version=None)       # uploads to next version

    # if args.outdir:
    #     os.makedirs(args.outdir, exist_ok=True)
    #     with open(os.path.join(args.outdir, 'boundingbox.csv'), 'w') as f_out:
    #         writer = csv.DictWriter(f_out, fieldnames=['entity_id', 'source', 'page', 'left', 'top', 'width', 'height'])
    #         writer.writeheader()
    #         for block in blocks:
    #             for sent in block.sents:
    #                 writer.writerow({'entity_id': 0, 'source': 'kyle_pdf', 'page': block.bbox.page,
    #                                  'left': block.bbox.left, 'top': block.bbox.top,
    #                                  'width': block.bbox.width, 'height': block.bbox.height})
    #
    #     with open(os.path.join(args.outdir, 'entity.csv'), 'w') as f_out:
    #         writer = csv.DictWriter(f_out, fieldnames=['paper_id', 'version', 'type', 'within_paper_id', 'source'])
    #         writer.writeheader()
    #         for block in blocks:
    #             writer.writerow({})
    #
    #
    #     with open(os.path.join(args.outdir, 'entitydata.csv', 'w')) as f_out:
    #         pass
    #
    #     with open(os.path.join(args.outdir, 'version.csv', 'w')) as f_out:
    #         writer = csv.DictWriter(f_out, fieldnames=['paper_id', 'index'])
    #         pass
