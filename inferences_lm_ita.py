# -*- coding: utf-8 -*-
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
from datasets import load_dataset, load_metric, Audio
import os
import numpy as np
import sys
import warnings

"""import the model, processor, tokenizer"""

print("loading saved model")
saved_model = AutoModelForCTC.from_pretrained("/data/disk1/data/erodegher/wav2vec2-large-xls-r-300m-italian-30/checkpoint-11847/", local_files_only = True)
saved_model.to("cuda")
print("loading tokenizer")
tokenizer = Wav2Vec2CTCTokenizer.from_pretrained("/data/disk1/data/erodegher/tokenizer_ita/", local_files_only = True)
print("loading processor")
processor = Wav2Vec2Processor.from_pretrained("/data/disk1/data/erodegher/wav2vec2-large-xls-r-300m-italian-30/checkpoint-11847/", local_files_only=True)

"""import test set"""
common_voice_test= load_dataset("common_voice", "it", data_dir="./cv-corpus-6.1-2020-12-11", split="test[:10]")

"""lower and no punctuation, downsampling"""
chars_to_remove_regex = '[\,\?\.\!\-\;\:\"\“\%\‘\”\�\°\(\)\–\…\\\[\]\«\»\\\/\^\<\>\~]'
def remove_special_characters(batch):
    batch["sentence"] = re.sub(chars_to_remove_regex, '', batch["sentence"]).lower()
    return batch
common_voice_test = common_voice_test.map(remove_special_characters)
common_voice_test = common_voice_test.cast_column("audio", Audio(sampling_rate=16_000))

"""import metrics"""
wer = load_metric("wer")
cer = load_metric("cer")

print("Preprocessing Dataset")
def prepare_dataset(batch):
    audio = batch["audio"]    
    batch["input_values"] = processor(audio["array"], sampling_rate=audio["sampling_rate"]).input_values[0]
    batch["input_length"] = len(batch["input_values"])
    with processor.as_target_processor():
        batch["labels"] = processor(batch["sentence"]).input_ids
    return batch

common_voice_test = common_voice_test.map(prepare_dataset, remove_columns=common_voice_test.column_names )
common_voice_test= common_voice_test.filter(lambda x : x < 5.0*16000, input_columns=["input_length"])


"""#Loading original Transcriptions, lower, remove punctuation, resampling"""
print("loading transcriptions")
common_voice_transcription= load_dataset("common_voice", "it", split="test[:10]")
common_voice_transcription = common_voice_transcription.map(remove_special_characters)
common_voice_transcription=common_voice_transcription.cast_column("audio", Audio(sampling_rate=16_000))
transcription=[ el for el in common_voice_transcription if len(el["audio"]["array"]) < 5.0*16000]

 
"""create vocab from tokenizer"""
vocab_dict = tokenizer.get_vocab()
sort_vocab = sorted((value, key) for (key,value) in vocab_dict.items())
vocab = [x[1].replace("|", " ") if x[1] not in tokenizer.all_special_tokens else "_" for x in sort_vocab]
print(vocab)
labels_ = [''.join(vocab)]
print(labels_)


print("""decoder from language model""")
import ctcdecode
from ctcdecode import CTCBeamDecoder

decoder = CTCBeamDecoder(labels= labels_,
                          model_path="/data/disk1/data/erodegher/ita.arpa" ,
                          #alpha=0,
                          #beta=0,
                          #cutoff_top_n=40,
                          #cutoff_prob=1.0,
                          #beam_width=128,
                          #num_processes=2,
                          blank_id=0,
                          log_probs_input=False
)

"""Evaluation"""
print('evaluation')
d_predictions={}
predictions = [ ]

for el in common_voice_test["input_values"]:
    input_dict = processor(el, return_tensors="pt", padding=True)
    logits = saved_model(input_dict.input_values.cuda()).logits
    print(logits.shape)
    pred_ids = torch.argmax(logits[0], dim=-1)    # here we apply a greedy algorithm to the output of wav2vec2, 
    #print(pred_ids)                              # we get the id with the highest probability
    predicted_sentences = processor.decode(pred_ids)
    predictions.append(predicted_sentences)
    #print(predictions)

    # feed the logits to your second model: ita.arpa
    beam_results, beam_scores, timesteps, out_lens = decoder.decode(logits.numpy())
    print(beam_results)
    

for i in range(50):
     print(beam_results[0][i][:out_len[0][i]])

#text = "".join[labels_[n] for n in beam_results[0][0][:out_len[0][0]]]
#print("LM Prediction: ", text)
#print("Prediction:", processor.batch_decode(predicted_ids))
#print("Reference: ", test_dataset[:10]["sentence"])

sys.exit()


"""compute CER WER"""

list_sent=[]
list_ref=[]
list_cer=[]
list_wer=[]
for i, sentence_ in enumerate(predictions):
    #print(i, sentence_)
    print("LM Prediction: ", text)
    print(i, "Sentence: ",  sentence_)
    print("Reference: ",  transcription[i]["sentence"])
    #result_cer= cer.compute(predictions=[sentence_], references=[transcription[i]["sentence"]])
    #result_wer= wer.compute(predictions=[sentence_], references=[transcription[i]["sentence"]])
    #print("CER: ", result_cer, "WER: ", result_wer)

    #list_sent.append(sentence_)
    #list_ref.append(transcription[i]["sentence"])
    #list_cer.append(result_cer)
    #list_wer.append(result_wer)

"""Write inference file """

#d={ "predictions":list_sent, "reference":list_ref }
#d2= {"CER score": [], "WER score": [] }
#print(d2)
#df = pd.DataFrame(d)
#df.to_csv("/data/disk1/data/erodegher/CSV_ITA_INFERENCES.csv")
