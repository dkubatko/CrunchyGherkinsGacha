IMAGE_GENERATOR_INSTRUCTION = """
Generate a flashy, creative collectible trading card based on the character in the attached image and the following description:
<{modification} {name}> with border color {color} and {rarity} rarity.

Rarity hierarchy is Common -> Rare -> Epic -> Legendary. Higher the Rarity, more sophisticated the card design should be.

Use comic book-like digital art style. Adjust the style based on the card name if needed.

You are free to modify the base image as much as you would like to fully reflect the description, but keep the face of the character consistent with the original image.
Fill the full image with the card, edge-to-edge, corners are square.

Do NOT add any stats, corner markers, etc. to the card. Do NOT include rarity information on the card.
Only add card name "{modification} {name}" to the bottom, no description.
"""

RARITIES = {
    "Common": {
        "weight": 65,
        "color": "blue",
        "modifiers": [
            "Relaxed",
            "Super",
            "Productive",
            "Young",
            "Old",
            "Hippie",
            "Business",
            "Evening",
            "Sleepy",
            "Cool",
            "Regular",
        ],
    },
    "Rare": {
        "weight": 20,
        "color": "green",
        "modifiers": [
            "Smoking",
            "Rich",
            "Magic",
            "Modern",
            "Hungry",
            "Angry",
            "Anxious",
            "Greedy",
            "Shiny",
            "Superhero",
            "Chilling",
        ],
    },
    "Epic": {
        "weight": 10,
        "color": "purple",
        "modifiers": [
            "Дикий",
            "Бритый",
            "Лакомящийся",
            "Хайповый",
            "Bored",
            "Overstimulated",
            "Sailor Moon",
            "Diamond",
            "Nuclear",
            "Anime",
            "Foil",
            "Noir",
            "JoJo",
            "Cringe",
        ],
    },
    "Legendary": {
        "weight": 5,
        "color": "golden",
        "modifiers": [
            "Мытый",
            "Кальянный",
            "Crunchy Gherkins",
            "Akatsuki",
            "Sigma",
            "Golden",
            "Black",
        ],
    },
}

REACTION_IN_PROGRESS = "🤔"

COLLECTION_CAPTION = (
    "<b>[{card_id}] {card_title}</b>\n"
    "Rarity: <b>{rarity}</b>\n\n"
    "<i>Showing {current_index}/{total_cards} owned by @{username}</i>"
)

CARD_CAPTION_BASE = "<b>[{card_id}] {card_title}</b>\nRarity: <b>{rarity}</b>"
CARD_STATUS_UNCLAIMED = "\n\n<i>Unclaimed</i>"
CARD_STATUS_CLAIMED = "\n\n<i>Claimed by @{username}</i>"
CARD_STATUS_ATTEMPTED = "\n<i>Attempted by: {users}</i>"

TRADE_REQUEST_MESSAGE = (
    "Trade requested:\n\n"
    "@{user1_username}'s\n<b>{card1_title}</b>\n\n"
    "🔄\n\n"
    "@{user2_username}'s\n<b>{card2_title}</b>"
)

TRADE_COMPLETE_MESSAGE = (
    "Trade completed:\n\n"
    "@{user1_username}'s\n<b>{card1_title}</b>\n\n"
    "🤝\n\n"
    "@{user2_username}'s\n<b>{card2_title}</b>"
)

TRADE_REJECTED_MESSAGE = (
    "Trade rejected:\n\n"
    "@{user1_username}'s\n<b>{card1_title}</b>\n\n"
    "🚫\n\n"
    "@{user2_username}'s\n<b>{card2_title}</b>"
)
