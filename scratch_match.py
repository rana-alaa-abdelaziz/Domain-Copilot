options = [
    "To create a reference to a DOM element",
    "To access the component's state",
    "To add React events to the component",
    "To remove React components from the DOM"
]
correct_answer = "A) To create a reference to a DOM element"

matched_option = next(
    (
        opt
        for opt in options
        if correct_answer.lower() in opt.lower()
        or opt.lower() in correct_answer.lower()
    ),
    options[0],
)
print("Matched option:", matched_option)
