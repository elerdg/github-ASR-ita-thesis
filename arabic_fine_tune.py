# -*- coding: utf-8 -*-

# Commented out IPython magic to ensure Python compatibility.
# %%capture 
# !pip install datasets==2.1
# !pip install transformers==4.18 
# !pip install huggingface_hub==0.5.1 
# !pip install torchaudio==0.11
# !pip install librosa 
# !pip install jiwer   
# ! git config --global credential.helper store 
# ! apt install git-lfs


import pandas as pd
from datasets import ClassLabel
import random
import re
import torch
import json
from IPython.display import display, HTML
from transformers import Wav2Vec2ForCTC
from transformers import Wav2Vec2CTCTokenizer
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from transformers import AutoModelForCTC, Wav2Vec2Processor
from datasets.utils.version import Version
from datasets import load_dataset, load_metric, Audio, load_from_disk
import os
import numpy as np
import sys
import argparse

parser = argparse.ArgumentParser(description="Script fine-tuning wav2vec2-xls-r with arabic transcribed speech data, the text cleaning process in the script is adapted to arabic writing.")
parser.add_argument('-tp','--train_pct', type=int, help='select the train pct', default=10)
arg= parser.parse_args()
train_pct= arg.train_pct


os.environ["WANDB_DISABLED"] = "true"

#"""load from /home/.cache/common_voice..."""
common_voice_train = load_dataset("common_voice", "ar" , split=f"train[:{train_pct}%]")
common_voice_train = common_voice_train.remove_columns(["accent", "age", "client_id", "down_votes", "gender", "locale", "segment", "up_votes"])

common_voice_test = load_dataset("common_voice", "ar", split="test[:10%]" )
common_voice_test = common_voice_test.remove_columns(["accent", "age", "client_id", "down_votes", "gender", "locale", "segment", "up_votes"])

common_voice_validation=load_dataset("common_voice",  "ar", split="validation[:10%]")
common_voice_validation=common_voice_validation.remove_columns(["accent", "age","client_id", "down_votes","gender","locale","segment","up_votes" ])
                            
"""the information are about : client id, path, audio file, the transcribed sentence , votes , age, gender , accent, the locale of the speaker, and segment """
len_train = len(common_voice_train)
len_test = len(common_voice_test)
len_validation=len(common_voice_validation)
print(f" FILE AUDIO PER SET    train: {len_train},        test: {len_test},     validation: {len_validation}")


"""## Preprocessing dataset"""
print('preprocessing the dataset')

chars_to_remove_regex = '[\???\,\?\.\!\-\;\:\"\???\%\???\??\(\)\???\???\??\??\,\""\???\???\???\~\??\??\??\,\???\??\??\???\,\???\???\???\???\???\???\???\???\[\]\{\}\=\`\_\+\<\>\???\???\??\??\???\???\???\???\???\???\???\???\???\???\???\???\???\???\???\???\???\???\???\??\/\\\???\^\'\??\??\??\??\???\???\'?? \'??\'??\'??\'??\'??]'

def remove_special_characters(batch):
    batch["sentence"] = re.sub(chars_to_remove_regex, ' ', batch["sentence"]).lower()
    return batch

common_voice_train = common_voice_train.map(remove_special_characters)
common_voice_test = common_voice_test.map(remove_special_characters)
common_voice_validation=common_voice_validation.map(remove_special_characters)

def replace_hatted_characters(batch):
    batch["sentence"] = re.sub('[??]', 'a', batch["sentence"])
    batch["sentence"] = re.sub('[??]', 'i', batch["sentence"])
    batch["sentence"] = re.sub('[??]', 'o', batch["sentence"])
    batch["sentence"] = re.sub('[??]', 'u', batch["sentence"])
    batch["sentence"] = re.sub('[??]', 'e', batch["sentence"])
    batch["sentence"] = re.sub('[??]', 'o', batch["sentence"])
    batch["sentence"] = re.sub('[??]','u', batch["sentence"])
    batch["sentence"] = re.sub('[??]', 'i', batch["sentence"])

    return batch
#common_voice_train = common_voice_train.map(replace_hatted_characters)
#common_voice_test = common_voice_test.map(replace_hatted_characters)
#common_voice_validation= common_voice_validation.map(replace_hatted_characters)

def extract_all_chars(batch):
  all_text = " ".join(batch["sentence"])
  vocab = list(set(all_text))
  return {"vocab": [vocab], "all_text": [all_text]}

vocab_train = common_voice_train.map(extract_all_chars, batched=True, batch_size=-1, keep_in_memory=True, remove_columns=common_voice_train.column_names)
vocab_test = common_voice_test.map(extract_all_chars, batched=True, batch_size=-1, keep_in_memory=True, remove_columns=common_voice_test.column_names)

#vocab_list = list(set(vocab_train["vocab"][0]) | set(vocab_test["vocab"][0]))
#vocab_dict = {v: k for k, v in enumerate(sorted(vocab_list))}
#print(vocab_dict)

"""for character not present in the test"""
#vocab_dict["|"] = vocab_dict[" "]
#del vocab_dict[" "]

"""### Vocab of Characters"""
#vocab_dict["[UNK]"] = len(vocab_dict)
#vocab_dict["[PAD]"] = len(vocab_dict)
#len(vocab_dict)

import json
#with open('vocab.json', 'w') as vocab_file:
    #json.dump(vocab_dict, vocab_file)

print("## Tokenizer")
from transformers import Wav2Vec2CTCTokenizer
#tokenizer = Wav2Vec2CTCTokenizer.from_pretrained("./", unk_token="[UNK]", pad_token="[PAD]", word_delimiter_token="|")
#tokenizer.save_pretrained("./wav2vec2-large-xls-r-300m-arabic-80")
print("load tokenizer from local folder: tokenizer_ar \n the tokenizer contains 40 characters: 37 + 3 special tokens ")
tokenizer= Wav2Vec2CTCTokenizer.from_pretrained("/data/disk1/data/erodegher/tokenizer_ar/", local_files_only=True)

"""## FeatureExtractor"""
from transformers import Wav2Vec2FeatureExtractor
feature_extractor = Wav2Vec2FeatureExtractor(feature_size=1, sampling_rate=16000, padding_value=0.0, do_normalize=True, return_attention_mask=True)

"""## Processor = feature extractor + tokenizer"""
from transformers import Wav2Vec2Processor, Wav2Vec2CTCTokenizer
processor = Wav2Vec2Processor(feature_extractor=feature_extractor, tokenizer=tokenizer)

print("## Check and resampling")
common_voice_train = common_voice_train.cast_column("audio", Audio(sampling_rate=16_000))
common_voice_test = common_voice_test.cast_column("audio", Audio(sampling_rate=16_000))
common_voice_validation = common_voice_validation.cast_column("audio", Audio(sampling_rate=16_000))

print("## Prepare Dataset")
def prepare_dataset(batch):
    audio = batch["audio"]
    # batched output is "un-batched"
    batch["input_values"] = processor(audio["array"], sampling_rate=audio["sampling_rate"]).input_values[0]
    batch["input_length"] = len(batch["input_values"])
    
    with processor.as_target_processor():
        batch["labels"] = processor(batch["sentence"]).input_ids
    return batch

common_voice_train = common_voice_train.map(prepare_dataset, remove_columns=common_voice_train.column_names)
common_voice_test = common_voice_test.map(prepare_dataset, remove_columns=common_voice_test.column_names)
common_voice_validation= common_voice_validation.map(prepare_dataset, remove_columns=common_voice_validation.column_names)

common_voice_train= common_voice_train.filter(lambda x:x < 5.0*processor.feature_extractor.sampling_rate, input_columns=["input_length"])
common_voice_test=common_voice_test.filter(lambda x:x < 5.0*processor.feature_extractor.sampling_rate, input_columns=["input_length"])
common_voice_validation=common_voice_validation.filter(lambda x:x < 5.0*processor.feature_extractor.sampling_rate, input_columns=["input_length"])
    
#""""Filtered Duration in seconds of TRAIN TEST AND VALIDATION sets""""
def Audio_len_filter(common_voice_set):
    len_t =0
    for el in common_voice_set:
        T= el["input_length"]/16000
        len_t= len_t +T
    return len_t

len_tr_filter = Audio_len_filter(common_voice_train)
len_ts_filter = Audio_len_filter(common_voice_test)
len_val_filter=Audio_len_filter(common_voice_validation)
print("filtered duration TRAIN in seconds ", len_tr_filter, " TEST in seconds", len_ts_filter , "VALIDATION in seconds", len_val_filter)  

"""## Data Collator """
import torch
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

@dataclass
class DataCollatorCTCWithPadding:
    """
    Data collator that will dynamically pad the inputs received.
    Args:
        processor (:class:`~transformers.Wav2Vec2Processor`)
            The processor used for proccessing the data.
        padding (:obj:`bool`, :obj:`str` or :class:`~transformers.tokenization_utils_base.PaddingStrategy`, `optional`, defaults to :obj:`True`):
            Select a strategy to pad the returned sequences (according to the model's padding side and padding index)
            among:
            * :obj:`True` or :obj:`'longest'`: Pad to the longest sequence in the batch (or no padding if only a single
              sequence if provided).
            * :obj:`'max_length'`: Pad to a maximum length specified with the argument :obj:`max_length` or to the
              maximum acceptable input length for the model if that argument is not provided.
            * :obj:`False` or :obj:`'do_not_pad'` (default): No padding (i.e., can output a batch with sequences of
              different lengths).
    """

    processor: Wav2Vec2Processor
    padding: Union[bool, str] = True

    def __call__(self, features: List[Dict[str, Union[List[int], torch.Tensor]]]) -> Dict[str, torch.Tensor]:
        # split inputs and labels since they have to be of different lenghts and need
        # different padding methods
        input_features = [{"input_values": feature["input_values"]} for feature in features]
        label_features = [{"input_ids": feature["labels"]} for feature in features]
            
        batch = self.processor.pad(
            input_features,
            padding=self.padding,
            return_tensors="pt",
        )
        with self.processor.as_target_processor():
            labels_batch = self.processor.pad(
                label_features,
                padding=self.padding,
                return_tensors="pt",
            )

        # replace padding with -100 to ignore loss correctly
        labels = labels_batch["input_ids"].masked_fill(labels_batch.attention_mask.ne(1), -100)

        batch["labels"] = labels

        return batch

data_collator = DataCollatorCTCWithPadding(processor=processor, padding=True)


"""## Cer Metric"""
cer_metric = load_metric("cer")
wer_metric = load_metric("wer")

def compute_metrics(pred):
    pred_logits = pred.predictions
    pred_ids = np.argmax(pred_logits, axis=-1)

    pred.label_ids[pred.label_ids == -100] = processor.tokenizer.pad_token_id
    pred_str = processor.batch_decode(pred_ids)
    # we do not want to group tokens when computing the metrics
    label_str = processor.batch_decode(pred.label_ids, group_tokens=False)

    cer = cer_metric.compute(predictions=pred_str, references=label_str)
    wer = wer_metric.compute(predictions=pred_str, references=label_str)

    print("wer:", wer)
    print("cer", cer)

    return {"cer": cer,
            "wer": wer,
    }

"""# load the pretrained checkpoint of Wav2Vec2-XLS-R-300M"""

print('loading pretrained model')
from transformers import Wav2Vec2ForCTC

model = Wav2Vec2ForCTC.from_pretrained(
    "facebook/wav2vec2-xls-r-300m", 
    attention_dropout=0.0,
    hidden_dropout=0.0,
    feat_proj_dropout=0.0,
    mask_time_prob=0.05,
    layerdrop=0.0,
    ctc_loss_reduction="mean", 
    pad_token_id=processor.tokenizer.pad_token_id,
    vocab_size=len(processor.tokenizer),
).cuda()

model.freeze_feature_extractor()


from transformers import TrainingArguments
training_args = TrainingArguments(
    output_dir=f"wav2vec2-large-xls-r-300m-arabic-{train_pct}",
  group_by_length=True,
  per_device_train_batch_size=4,
  per_device_eval_batch_size=4,
  gradient_accumulation_steps=2,
  evaluation_strategy="epoch",
  num_train_epochs=80,
  gradient_checkpointing=True,
  fp16=True,
  #save_steps=400,
  #eval_steps=400,
  #logging_steps=400,
  learning_rate=3e-4,
  warmup_steps=500,
  save_total_limit=2,
  save_strategy= "epoch",
  metric_for_best_model="eval_loss",
  load_best_model_at_end = True,
)

from transformers import Trainer, EarlyStoppingCallback

trainer = Trainer(
    model=model,
    data_collator=data_collator,
    args=training_args,
    compute_metrics=compute_metrics,
    train_dataset=common_voice_train, 
    eval_dataset=common_voice_validation,
    tokenizer=processor.feature_extractor,
    callbacks= [EarlyStoppingCallback(early_stopping_patience = 3)],
)


"""# Training """
print("TRAINING")
trainer.train()
#trainer.train(resume_from_checkpoint=True )
print("ENDED TRAINING")

"""#Save Model"""
print("Saving Model and Tokenizer")


"""# Evaluation"""
print('evaluation')

input_dict = processor(common_voice_test[0]["input_values"], return_tensors="pt", padding=True)
logits = model(input_dict.input_values.cuda()).logits
pred_ids = torch.argmax(logits, dim=-1)[0]
print("PRED_IDS", pred_ids)

print("Prediction:")
print(processor.decode(pred_ids))

common_voice_test_transcription = load_dataset("common_voice", "ar", data_dir="./cv-corpus-6.1-2020-12-11", split="test[:10%]")
print("\nReference:")
print(common_voice_test_transcription[0]["sentence"].lower())
