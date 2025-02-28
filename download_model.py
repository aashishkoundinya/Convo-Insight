from transformers import AutoTokenizer, AutoModelForCausalLM

# Use a smaller causal language model
model_name = "Qwen/Qwen2-0.5B-Instruct"  # Only 0.5B parameters
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

print(f"Successfully downloaded {model_name}")