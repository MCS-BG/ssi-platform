# Day 9 — How a model learns

The lab so far answers from notes. Retrieval-augmented generation puts a few chunks of those notes into the prompt, and `llama3.2:3b` talks from that prompt. That does not change the model. The weights on disk are the same file they were after the pull.

This lesson is the other question: what people mean by "update the model," which of those meanings is actually learning, which models this GPU can load, and how a later fine-tune would be shaped. It does not train anything. It does not pull or delete a model. It does not touch `nomic-embed-text` or its keep-alive.

## The lab at a glance

- **Terminal:** `kubectl` through the SSH tunnel that is already open, with the existing `KUBECONFIG`. This lesson does not open a new tunnel.
- **Lab host:** node `gpu-node` on the k3s cluster. Ollama and Open WebUI run here. The GPU is an NVIDIA laptop GPU with 4 GB of VRAM.
- **What is serving:** chat is `llama3.2:3b`. Embeddings are `nomic-embed-text`, pinned with keep-alive forever. Both stay as they are.
- **What fits:** local models stay about 1B to 4B, quantized. A 7B model at 4-bit is the ceiling, and it is tight. This lesson does not fine-tune the model that is serving chat.

## Three different meanings of "update the model"

Only the third meaning changes weights. The path this lab has actually taken is the second one.

### Swap the Ollama model

Swapping means serving a different file that somebody else already trained. `ollama pull` downloads that file, and the next request can name it. The new file has different weights, but nothing on this machine learned them. They were frozen before the download. On 4 GB that swap is feasible only for a small quantized model, about 1B to 4B. A 7B model at 4-bit is the ceiling, and it is tight, because the weights and the context cache share the card, and the pinned embedding model already wants room. One chat model at a time. This lesson does not pull one.

### Change what it sees

A system prompt, and RAG, change the text in front of the model. The forward pass is different because the input is different. The weight file is not. Day 4 is this meaning: notes are embedded, stored, retrieved, and pasted into the prompt. When the notes change, the answers can change, and `llama3.2:3b` is still the same weights. That is the right tool for lab facts that go stale. It is feasible on this GPU because it is inference, which this cluster already does. It is not learning.

### Change the weights

Learning means a training run writes new numbers into the model, or into a small adapter that sits on top of it. Four names show up for that, and they are not the same job.

Continued pretraining keeps training the model on raw text, the way it was first trained, so it gets more fluent in a body of writing. It updates the full weights. It wants a lot of text and a lot of compute. It is not feasible on a 4 GB card, and it is the wrong tool for "answer in my house style."

Supervised fine-tuning uses pairs: here is the question, here is the answer to imitate. A full supervised run also updates every weight. A 3B model in 16-bit does not fit in 4 GB for that. The serving chat model is the wrong target even if it did.

LoRA and QLoRA freeze the original weights and train a small add-on instead of the whole file. LoRA still wants the base model in a training precision, so a 3B base does not become cheap just because the add-on is small. QLoRA keeps that frozen base in a 4-bit form and trains the add-on, which is the only weight-update that is even worth planning on hardware this small. On this card it is still not a quality run against the model that is serving chat, and it must not be done inside the Ollama pod. A later run uses a separate tiny open model, on a machine with more VRAM, or as a tiny CPU run whose only purpose is to watch the loss go down.

Preference tuning trains from a better answer and a worse answer to the same question, not from a single target reply. Names like RLHF and DPO are this family. It is still a weight update, it needs a harder dataset than plain question and answer pairs, and it is not feasible here as a real run. It is not the first experiment.

## How learning actually works

A model is a long list of weights, decimal numbers in a file. Inference does not edit that list. Training does.

A forward pass puts an input through those numbers and produces a guess. For a question-and-answer pair, the guess is the next tokens of the reply. The loss is a single score of how far that guess was from the reply written in the training pair. Lower is closer. A backward pass walks that score back through the network and records which weights to nudge. An optimizer step applies a small nudge, then the next pair runs the same loop. After enough steps the file on disk is not the file that started. That is the whole idea. There is no separate "memory" being written beside the weights, unless the method is an adapter, and then the adapter is the piece that changed.

A 4 GB card cannot full-fine-tune even a 3B model in 16-bit, because training has to hold the activations from the forward pass and the optimizer state, which is extra copies of the weights, not just the weight file that inference would load.

## Which models can be loaded

Ollama runs open-weight models only. The families that have a small quantized build in the 1B to 4B range, and so can fit this card, include Llama, Mistral, Gemma, Qwen, and Phi, plus similar small families such as Granite or SmolLM when a small build exists. A 7B model at 4-bit is the ceiling and it is tight, not the default choice. The embedding model is not a chat model. Leave `nomic-embed-text` alone.

Check `ollama pull` names in the Ollama library rather than inventing a tag. A name that looks plausible can be a tag that was never published, or a size that does not fit.

"Available in Ollama" means someone published weights and a manifest the Ollama library can download. It does not mean Meta, Mistral, Google, Alibaba, Microsoft, or anyone else hosts this cluster's runtime. The process that multiplies those weights is the Ollama container on node `gpu-node`.

## Closed models

Grok, ChatGPT in the GPT-4 class, Gemini, and Claude cannot be loaded into Ollama, and they cannot be loaded onto this GPU. There are no public weights to pull. Quantizing them is not a missing step. The file does not exist outside the vendor.

Open WebUI can add them as remote OpenAI-compatible connections, or as that provider's own connection type. The browser still talks to Open WebUI on the lab. Open WebUI then sends the prompt off the machine to the vendor, and the reply comes back. That is not a local model with a different name. Data leaves the machine: the prompt, and whatever context the UI attaches, are no longer only on the lab host.

I am not putting a key, an endpoint that carries a secret, or signup steps in this lab. Adding a remote provider later is a privacy decision before it is a quality decision.

## The lab

Two parts. Part A is the only command, and it is read-only. Part B is the shape of a later run. Do not train today.

### Part A: what Ollama already has

Use the tunnel and `KUBECONFIG` that are already set on the terminal. The command execs into the Ollama pod in namespace `si-lab` (the pod on node `gpu-node`, selected as `deploy/ollama`) and lists models. It does not load a model, unload one, pull, delete, or change keep-alive.

Terminal
```bash
kubectl -n si-lab exec deploy/ollama -- ollama list
```

Read the header that comes back. On the builds this lab has already used, the columns are:

- **NAME** is the model and tag, such as `llama3.2:3b`. That is the string a request has to use.
- **ID** is a short id of the file Ollama stored. It is not a quality score.
- **SIZE** is disk space for that model. It is not the VRAM a loaded model would use, and it is not a training result.
- **MODIFIED** is when that entry was pulled or created locally. It is not "last time the model learned."

If a newer Ollama prints a different header, trust the header on screen. Expect `llama3.2:3b` and `nomic-embed-text` to be present. Anything else in the list is just already downloaded. Do not delete it in this lesson, and do not pull a neighbor to "complete the set." Nothing in this list is a fine-tune.

### Part B: the shape of a later run

This part is not a run. There is no known-good learning rate, LoRA rank, or epoch count for a dataset that does not exist yet. When the time comes, I start from the QLoRA defaults of the tool I pick, Unsloth or Hugging Face TRL, and I watch the loss. I do not copy magic numbers from a blog.

The later run looks like this.

I pick a separate tiny open model, not `llama3.2:3b` and not `nomic-embed-text`. The serving chat model stays the general model. The experiment is a second model that is allowed to be narrow and bad at everything else.

I write a few dozen of my own question and answer pairs, in a jsonl file, one pair per line, with `instruction` and `response`. A few dozen is enough to teach a habit, not enough to replace a general model. I hold some pairs out before any training, and those held-out lines never go in the training file. The shape of one training line is:

```text
{"instruction": "When I ask for a lab status line, what shape should the answer take?", "response": "One sentence: node, GPU, and whether Ollama is up. No extra advice."}
```

That line is an example of the fields, not a pair from this lab and not something to train on.

I train on a machine with more VRAM than 4 GB if I have one. If the only option is this lab, I accept a tiny CPU run whose only job is to see the loss go down. I do not run that inside the Ollama pod, and I do not take the GPU away from the chat model and the pinned embedding model. A 4 GB fine-tune will not beat `llama3.2:3b` at general questions. It only teaches a narrow habit, and only if the pairs actually agree with each other.

When a run has produced an adapter, I export a GGUF of the merged tiny model and bring that file back as a new Ollama model, using a Modelfile. I do not invent a chat template. I copy the template from the base model's own Modelfile when I build this later. The Modelfile shape is:

```text
FROM ./habit.gguf
SYSTEM You follow only the narrow habit in the pairs you were trained on. You are not the general chat model.
```

`FROM` points at the GGUF I exported. `SYSTEM` is optional and should describe the habit, not a fantasy of general skill. Creating it is a later command of the form `ollama create <name> -f Modelfile`, aimed at whichever Ollama should hold the experiment. Creating it in the cluster Ollama makes the name show up in Open WebUI's list, because Open WebUI lists what that Ollama has. I do not select it, and I do not point the RAG worker at it, until the comparison in the next section is done.

## How to know it learned

I do not trust a vibe, and I do not trust a public benchmark number I did not run.

I watch two losses. Training loss should go down, which only means the model is getting closer to pairs it is allowed to see. Held-out loss should be computed on my own questions that were split out before training and never written into the training file. If training loss falls and held-out loss does not, it memorized the file. If both stay flat, the run did not learn the habit. No target number is claimed here, because none has been measured on my pairs.

Then I ask one question that is not in the training file, and I write down the answer from the untouched tiny base model and the answer from the adapted model. The adapted answer should show the habit the pairs taught, on a question the file did not contain. If the two answers match, or the new one only changed on questions that were copied into the file, it did not learn. General questions are the wrong test. This experiment is not supposed to win those against `llama3.2:3b`.

## How this maps to Azure

Closed models stay at the vendor. Azure OpenAI fine-tuning submits my pairs to Azure and serves the result as a deployment in that resource. I would call that deployment. I still do not get the weights.

Open weights are the other Azure path: a GPU VM, or an AKS node pool, with more VRAM than this 4 GB card. QLoRA runs there, the GGUF comes home if the model license allows, and Ollama on node `gpu-node` only sees the exported file. The serving chat model on the lab host is still not the training job.

## AWS delta

The closed-model equivalent is a Bedrock custom model: training stays in the account, and I still do not get the base weights out. The open-weight equivalent is a larger EC2 GPU than this card, then the same export back to a GGUF and `ollama create`. Either way, a fine-tune at the vendor is not a file I can load on the lab GPU.

## What this lab deliberately does not do

It does not replace RAG. Notes still belong in retrieval, because retrieval can change without a training run, and a fine-tune does not know a fact that was never in its pairs.

It does not change Prompt Guard. The guard stays in the request path, at the same threshold, fail closed, whether the model is `llama3.2:3b` or some later experiment.

It does not point Open WebUI at the experiment. The chat default stays `llama3.2:3b` until a held-out loss and a before-and-after answer, on a question that was not in the training file, show that the new weights did something real.
