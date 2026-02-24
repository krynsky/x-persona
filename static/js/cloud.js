/**
 * X Persona — Interactive Word Cloud
 * Handles word click drill-down via the /api/lists-for-word endpoint.
 */

let activeWord = null;

// Vibrant color palette for word cloud
const CLOUD_COLORS = [
    '#e74c3c', // red
    '#e67e22', // orange
    '#f1c40f', // yellow
    '#2ecc71', // green
    '#1abc9c', // teal
    '#3498db', // blue
    '#1d9bf0', // X blue
    '#9b59b6', // purple
    '#e84393', // pink
    '#00cec9', // cyan
    '#fd79a8', // salmon pink
    '#6c5ce7', // indigo
    '#a29bfe', // lavender
    '#55efc4', // mint
    '#ffeaa7', // pale yellow
    '#fab1a0', // peach
    '#74b9ff', // light blue
    '#ff7675', // coral
    '#dfe6e9', // light gray
    '#b2bec3', // gray
];

/**
 * Assign a random color from the palette to each word, ensuring
 * no two adjacent words share the same color.
 */
function colorizeCloud() {
    const words = document.querySelectorAll('.cloud-word');
    let lastColor = '';
    words.forEach(el => {
        let color;
        do {
            color = CLOUD_COLORS[Math.floor(Math.random() * CLOUD_COLORS.length)];
        } while (color === lastColor && CLOUD_COLORS.length > 1);
        el.style.color = color;
        el.dataset.color = color; // store for restoring after active state
        lastColor = color;
    });
}

async function showListsForWord(word) {
    const panel = document.getElementById('drill_down');
    const wordEl = document.querySelector(`.cloud-word[data-word="${word}"]`);

    // Toggle off if clicking the same word
    if (activeWord === word) {
        closeDrillDown();
        return;
    }

    // Clear previous active state and restore original color
    document.querySelectorAll('.cloud-word.active').forEach(el => {
        el.classList.remove('active');
        el.style.color = el.dataset.color || '';
    });

    // Set new active
    activeWord = word;
    if (wordEl) wordEl.classList.add('active');

    // Fetch matching lists
    try {
        const resp = await fetch(`/api/lists-for-word?username=${PROFILE_USERNAME}&word=${encodeURIComponent(word)}`);
        const data = await resp.json();

        if (data.error) {
            console.error(data.error);
            return;
        }

        // Update panel header
        document.getElementById('drill_word').textContent = word;
        document.getElementById('drill_count').textContent = `Appears in ${data.count} list${data.count !== 1 ? 's' : ''}`;

        // Build list items
        const body = document.getElementById('drill_lists');
        body.innerHTML = data.lists.map(lst => `
            <div class="drill-list-item">
                <div>
                    <div class="drill-list-name">${escapeHtml(lst.name)}</div>
                    <div class="drill-list-owner">by @${escapeHtml(lst.owner)}</div>
                </div>
                <a href="https://x.com/i/lists/${lst.id}" target="_blank" class="table-link">View ↗</a>
            </div>
        `).join('');

        // Show panel
        panel.style.display = 'block';
        panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    } catch (err) {
        console.error('Error fetching lists:', err);
    }
}

function closeDrillDown() {
    const panel = document.getElementById('drill_down');
    if (panel) panel.style.display = 'none';

    document.querySelectorAll('.cloud-word.active').forEach(el => {
        el.classList.remove('active');
        el.style.color = el.dataset.color || '';
    });
    activeWord = null;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Colorize on page load
document.addEventListener('DOMContentLoaded', colorizeCloud);
