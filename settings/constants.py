IMAGE_GENERATOR_INSTRUCTION = """
Generate a flashy, creative collectible trading card based on the character in the attached image.
<{modification} {name}> with border color {color}.

You are free to modify the base image as much as you would like to fully reflect the description, but keep the face of the character consistent.
Fill the full image with the card, edge-to-edge, corners are square.

Do NOT add any stats, corner markers, etc. to the card.
Only add card name "{modification} {name}" to the bottom, no description.
"""

REACTION_IN_PROGRESS = "🤔"

RARITIES = {
    "Common": {"weight": 65, "color": "blue"},
    "Rare": {"weight": 20, "color": "green"},
    "Epic": {"weight": 10, "color": "purple"},
    "Legendary": {"weight": 5, "color": "golden"},
}

MODIFIERS = [
    "Дикий",
    "Мытый",
    "Бритый",
    "Выигрышный",
    "Куксящийся",
    "Лакомящийся",
    "Крутой",
    "Вчера",
    "Завтра",
    "Overstimulated",
    "Sailor Moon",
    "Super",
    "Anxious",
    "Productive",
    "Mexican",
    "Angry",
    "Shiny",
    "Greedy",
    "Old",
    "Young",
    "Swimming",
    "Diamond",
    "Superhero",
]
