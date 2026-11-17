async function feedback(userId, articleId, value, btn) {
  try {
    const res = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, article_id: articleId, value: value }),
    });
    if (!res.ok) throw new Error(await res.text());
    btn.classList.add('done');
    if (value < 0) document.getElementById('art-' + articleId).classList.add('faded');
  } catch (err) {
    alert('Could not save feedback: ' + err.message);
  }
}
