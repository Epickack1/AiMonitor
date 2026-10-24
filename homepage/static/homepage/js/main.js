// Текущий год в подвале страницы.
const yearElement = document.getElementById("current-year");
if (yearElement) {
    yearElement.textContent = new Date().getFullYear();
}

// Кнопки «скопировать id модели»: id нужен для запросов к OpenRouter.
document.querySelectorAll(".copy-id").forEach((button) => {
    button.addEventListener("click", () => {
        navigator.clipboard.writeText(button.dataset.modelId).then(() => {
            button.classList.add("copied");
            button.textContent = "✓";
            setTimeout(() => {
                button.classList.remove("copied");
                button.textContent = "⧉";
            }, 1500);
        });
    });
});
