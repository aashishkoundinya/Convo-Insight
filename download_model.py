from transformers import AutoTokenizer, AutoModelForCausalLM

model_name = "Qwen/Qwen2-1.5B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

print(f"Successfully downloaded {model_name}")