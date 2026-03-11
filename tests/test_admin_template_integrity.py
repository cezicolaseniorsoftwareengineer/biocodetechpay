"""
Static analysis tests for admin.html template.
Proves the delete modal CSS/JS fix is correctly applied.
No server or database required.
"""
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent.parent / "app" / "templates" / "admin.html"


def _html():
    return TEMPLATE_PATH.read_text(encoding="utf-8")


class TestDeleteModalTemplateIntegrity:

    def test_modal_uses_inline_display_none_not_tailwind_hidden(self):
        """Modal must use style='display:none' — Tailwind hidden class causes JIT CDN failure."""
        html = _html()
        modal_start = html.index('id="delete-confirm-modal"')
        modal_tag = html[modal_start - 5: modal_start + 400]

        assert "display:none" in modal_tag, (
            "Modal delete-confirm-modal must have style='display:none'. "
            "Tailwind JIT CDN does not generate .flex if it only appears in JS."
        )
        assert '"hidden' not in modal_tag.split("style=")[0], (
            "Modal must NOT have 'hidden' Tailwind class — it prevents flex display."
        )

    def test_confirm_delete_user_uses_style_display(self):
        """confirmDeleteUser must set modal.style.display = 'flex', not classList manipulation."""
        html = _html()
        fn_start = html.index("function confirmDeleteUser")
        fn_block = html[fn_start: fn_start + 500]

        assert "modal.style.display = 'flex'" in fn_block, (
            "confirmDeleteUser must use style.display = 'flex' to show the modal."
        )
        assert "classList.add('flex')" not in fn_block, (
            "classList.add('flex') fails with Tailwind CDN JIT — must use style.display."
        )

    def test_close_delete_modal_uses_style_display(self):
        """closeDeleteModal must set style.display = 'none', not classList manipulation."""
        html = _html()
        fn_start = html.index("function closeDeleteModal")
        fn_block = html[fn_start: fn_start + 300]

        assert "style.display = 'none'" in fn_block, (
            "closeDeleteModal must use style.display = 'none' to hide the modal."
        )
        assert "classList.add('hidden')" not in fn_block, (
            "classList.add('hidden') should not be used — use style.display instead."
        )

    def test_execute_delete_user_calls_correct_api_endpoint(self):
        """executeDeleteUser must call DELETE /admin/users/${userId}."""
        html = _html()
        fn_start = html.index("async function executeDeleteUser")
        fn_block = html[fn_start: fn_start + 500]

        assert "method: 'DELETE'" in fn_block, "executeDeleteUser must use DELETE method."
        assert "/admin/users/${userId}" in fn_block, (
            "DELETE must target /admin/users/{id}, not another endpoint."
        )
        assert "window.location.reload()" in fn_block, (
            "On success, page must reload to reflect the deletion."
        )

    def test_delete_button_triggers_correct_function(self):
        """Both desktop and mobile Excluir buttons must call confirmDeleteUser."""
        html = _html()
        occurrences = html.count("confirmDeleteUser")

        # 1 function definition + 2 onclick attributes (desktop table + mobile card)
        assert occurrences >= 3, (
            f"Expected at least 3 references to confirmDeleteUser, found {occurrences}. "
            "Desktop and/or mobile Excluir button may be missing onclick handler."
        )

    def test_detail_modal_also_uses_inline_style(self):
        """detail-modal must also use display:none for consistency."""
        html = _html()
        modal_start = html.index('id="detail-modal"')
        modal_tag = html[modal_start - 5: modal_start + 200]

        assert "display:none" in modal_tag, (
            "detail-modal must also use style='display:none'."
        )
