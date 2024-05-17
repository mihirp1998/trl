# this file deals with dataset pre-processing before training

# 1. PPO (prompt)
# 2. SFT (prompt + demonstration), there is also packing.
# 3. ✅ RM / DPO (chosen and rejected)
# 4. ✅ Visualization of length distributions?
# 5. ✅ Filter?
#   * Smart truncation?
# 6. ✅ dataset_num_proc
# 7. check EOS token
# 8. dataset mixer?
# 9. ✅ pretty print that show tokenization?
# 10. hashable tokneization?
# 11. inputs / labels / attention_mask
# 12. always set a `tokenizer.pad_token_id`?

## too many names related to "maximum length":
# * `max_seq_length` in SFT
# * `max_length`, `max_target_length` in RM / DPO,
# * `max_prompt_length` in DPO

import logging
from dataclasses import dataclass
from typing import Optional

import matplotlib.pyplot as plt
from datasets import Dataset
from rich.console import Console
from rich.text import Text
from transformers import PreTrainedTokenizer


COLORS = ["on red", "on green", "on blue", "on yellow", "on magenta"]


@dataclass
class DatasetConfig:
    max_token_length: Optional[int] = None
    max_prompt_token_lenth: Optional[int] = None

    # dataset.map config
    batched: bool = False
    load_from_cache_file: bool = False
    num_proc: Optional[int] = 1

    # visualization configs
    ncols: int = 2


class DatasetProcessor:
    def __init__(self, tokenizer: PreTrainedTokenizer, config: DatasetConfig) -> None:
        self.tokenizer = tokenizer
        self.config = config
        if self.tokenizer.pad_token_id == self.tokenizer.eos_token_id:
            logging.warn(
                "Tokenizer's pad token is the same as EOS token, this might cause the model to not learn to generate EOS tokens."
            )

    def tokenize(self, dataset: Dataset):
        raise NotImplementedError

    def filter(self, dataset: Dataset):
        if self.config is None:
            logging.warn("No config provided, skipping filtering")
            return dataset
        raise NotImplementedError

    def get_token_length_stats(self, features: list[str], dataset: Dataset):
        stats = {}
        for key in features:
            stats[key] = {
                "max_token_length": max(len(x) for x in dataset[key]),
                "min_token_length": min(len(x) for x in dataset[key]),
                "mean_token_length": sum(len(x) for x in dataset[key]) / len(dataset[key]),
            }
        return stats

    def get_token_length_visualization(
        self, features: list[str], dataset: Dataset, save_path: str = "tmp.png", bins: int = 30
    ):
        plt.figure(figsize=(10, 5))

        for feature in features:
            token_lengths = [len(x) for x in dataset[feature]]

            # Plot the histogram of token lengths
            plt.hist(token_lengths, bins=bins, alpha=0.5, label=feature, edgecolor="black")

        # Add title and labels
        plt.title("Token Length Distribution")
        plt.xlabel("Token Length")
        plt.ylabel("Frequency")
        plt.legend(loc="upper right")
        # Show the plot
        plt.savefig(save_path)
        logging.info(f"Saved token length distribution plot to {save_path}")


class PreferenceDatasetProcessor(DatasetProcessor):
    def tokenize(self, dataset: Dataset):
        def tokenize_fn(row):
            row["prompt"] = self.tokenizer.apply_chat_template(row["chosen"][:-1])
            row["chosen"] = self.tokenizer.apply_chat_template(row["chosen"])
            row["rejected"] = self.tokenizer.apply_chat_template(row["rejected"])
            return row

        return dataset.map(
            tokenize_fn, num_proc=self.config.num_proc, load_from_cache_file=self.config.load_from_cache_file
        )

    def filter(self, dataset: Dataset):
        def filter_fn(row):
            return (
                len(row["prompt"]) <= self.config.max_prompt_token_lenth
                if self.config.max_prompt_token_lenth is not None
                else True and len(row["chosen"]) <= self.config.max_token_length
                if self.config.max_token_length is not None
                else True and len(row["rejected"]) <= self.config.max_token_length
                if self.config.max_token_length is not None
                else True
            )

        return dataset.filter(
            filter_fn, num_proc=self.config.num_proc, load_from_cache_file=self.config.load_from_cache_file
        )

    def get_token_length_stats(self, dataset: Dataset):
        return super().get_token_length_stats(features=["prompt", "chosen", "rejected"], dataset=dataset)

    def get_token_length_visualization(self, dataset: Dataset):
        return super().get_token_length_visualization(features=["prompt", "chosen", "rejected"], dataset=dataset)


class SFTDatasetProcessor(DatasetProcessor):
    def tokenize(self, dataset: Dataset):
        def tokenize_fn(row):
            row["prompt"] = self.tokenizer.apply_chat_template(row["messages"][:-1])
            row["messages"] = self.tokenizer.apply_chat_template(row["messages"])
            return row

        return dataset.map(
            tokenize_fn, num_proc=self.config.num_proc, load_from_cache_file=self.config.load_from_cache_file
        )

    def filter(self, dataset: Dataset):
        def filter_fn(row):
            return (
                len(row["prompt"]) <= self.config.max_prompt_token_lenth
                if self.config.max_prompt_token_lenth is not None
                else True and len(row["messages"]) <= self.config.max_token_length
                if self.config.max_token_length is not None
                else True
            )

        return dataset.filter(
            filter_fn, num_proc=self.config.num_proc, load_from_cache_file=self.config.load_from_cache_file
        )

    def get_token_length_stats(self, dataset: Dataset):
        return super().get_token_length_stats(features=["prompt", "messages"], dataset=dataset)

    def get_token_length_visualization(self, dataset: Dataset):
        return super().get_token_length_visualization(features=["prompt", "messages"], dataset=dataset)


def visualize_token(tokens: list[int], tokenizer: PreTrainedTokenizer):
    i = 0
    console = Console()
    rich_text = Text()
    for i, token in enumerate(tokens):
        color = COLORS[i % len(COLORS)]
        decoded_token = tokenizer.decode(token)
        rich_text.append(f"{decoded_token}", style=color)
    console.print(rich_text)