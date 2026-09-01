from api_utils import (
    PromptCommentDTO,
    PromptDTO,
    PromptImpressionAction,
    PromptStatus,
    Permission,
    TagSubscriptionDTO,
    UpdatePromptImpressionDTO,
    UpdatePromptStatusDTO,
    UpdateTagDTO,
    UpdateUserDTO,
    UpdateUserImpressionDTO,
    UserImpressionAction,
    create_prompt,
    create_prompt_comment,
    create_tag_subscription,
    find_tag,
    get_dummy_user_token,
    is_prod,
    update_prompt_impression,
    update_prompt_status,
    update_dynamodb_item,
    update_tag,
    update_user,
    update_user_impression,
    upsert_user_by_user_token,
)


def create_dummy_fixtures(req=None) -> None:
    import random
    if is_prod():
        return
    created_prompts = []
    created_users = []
    generated_image_filenames = [
        "3d7af01f-819e-4c2f-bc69-eb7245b76a74_1809x1247.png",
        "45e97e68-a321-4657-9956-e942d9d757a7_1279x518.png",
        "4fdd2dcc-8c7d-40ac-80a6-647c828af338_1000x376.png",
        "5b027ec7-c018-4744-9eda-00abf75cf685_1111x712.png",
        "6a5118c0-a073-483b-ac5b-79e0a554e703_988x494.png",
        "a167891d-7e91-40d6-a5c4-1a3ddb27dcc2_1575x842.png",
        "ebdbe93d-99ec-4a47-b821-f4dfe0da769b_798x475.png",
    ]
    used_user_names = {"John Doe"}
    used_prompt_titles = set()
    first_names = ["Lorem", "Ipsum", "Dolor", "Amet", "Consectetur", "Adipiscing", "Elit"]
    last_names = ["Systems", "Patterns", "Scalability", "Reliability", "Architecture", "Telemetry", "Networks"]
    title_openers = ["Designing", "Building", "Exploring", "Modeling", "Operating", "Scaling", "Evolving"]
    title_subjects = ["Reliable Event Pipelines", "Distributed Data Planes", "Resilient Service Boundaries", "Adaptive Storage Systems", "Observable Control Loops", "Fault Tolerant Workflows", "Composable Platform Primitives"]
    title_endings = ["with Practical Constraints", "for Fast-Growing Systems", "under Real-World Load", "from First Principles", "without Losing Simplicity", "for Teams That Ship"]
    fixture_tag_names = [
        "distributed-systems", "event-driven", "cloud-architecture", "databases",
        "devops", "software-design", "observability", "reliability", "api-design",
        "backend", "frontend", "testing", "security", "performance", "automation",
        "containers", "kubernetes", "serverless", "messaging", "networking",
        "data-engineering", "machine-learning", "open-source", "teamwork",
    ]
    unused_fixture_tags = fixture_tag_names.copy()
    content_openers = ["A useful starting point is", "The practical challenge is", "In a production system", "A resilient design keeps", "The simplest approach begins with", "Over time, teams discover that"]
    content_subjects = ["clear ownership", "small feedback loops", "explicit boundaries", "measurable failure modes", "repeatable deployments", "well-defined contracts", "careful capacity planning"]
    content_actions = ["reduces unnecessary coordination", "makes failures easier to isolate", "keeps operational work visible", "creates room for gradual change", "turns assumptions into testable decisions", "helps teams compare trade-offs"]
    content_endings = ["before the system becomes difficult to change.", "without hiding important constraints.", "while keeping the implementation understandable.", "even when traffic and team size increase.", "so the result remains useful beyond the first release."]

    def unique_user_name() -> str:
        while True:
            name = f"{random.choice(first_names)} {random.choice(last_names)}"
            if name not in used_user_names:
                used_user_names.add(name)
                return name

    def unique_prompt_title() -> str:
        while True:
            title = f"{random.choice(title_openers)} {random.choice(title_subjects)} {random.choice(title_endings)}"
            if title not in used_prompt_titles:
                used_prompt_titles.add(title)
                return title
    def random_prompt_tags() -> list[str]:
        required_tag = unused_fixture_tags.pop(random.randrange(len(unused_fixture_tags))) if unused_fixture_tags else None
        available_tags = [tag for tag in fixture_tag_names if tag != required_tag]
        extra_tags = random.sample(available_tags, random.randint(0, 2))
        return [required_tag, *extra_tags] if required_tag else random.sample(fixture_tag_names, random.randint(1, 3))

    def random_figure(alt: str) -> str:
        if random.random() >= 0.5:
            return ""
        filename = random.choice(generated_image_filenames)
        return f"<img src=\"/{filename}\" alt=\"{alt}\">"

    def random_prompt_content(alt: str) -> str:
        paragraphs = []
        for _ in range(random.randint(10, 16)):
            sentences = [
                f"{random.choice(content_openers)} {random.choice(content_subjects)} "
                f"{random.choice(content_actions)} {random.choice(content_endings)}"
                for _ in range(random.randint(4, 7))
            ]
            paragraphs.append("<p>" + " ".join(sentences) + "</p>")
        content = "".join(paragraphs)
        while len(content) < 5000:
            sentence = ("<p>" + f"{random.choice(content_openers)} {random.choice(content_subjects)} "
                        f"{random.choice(content_actions)} {random.choice(content_endings)} "
                        f"{random.choice(content_openers)} {random.choice(content_subjects)} "
                        f"{random.choice(content_actions)} {random.choice(content_endings)}</p>")
            content += sentence
        return random_figure(alt) + content

    user_token = get_dummy_user_token()
    root_user = upsert_user_by_user_token(user_token)
    created_users.append(root_user)
    update_dynamodb_item((f"USER#{root_user.id}", "META"), {"permissions": [Permission.ROOT]})
    root_user.permissions = [Permission.ROOT]
    update_user_dto = UpdateUserDTO(
        name="John Doe",
        avatar_action="replace",
        image_filename="5b027ec7-c018-4744-9eda-00abf75cf685_1111x712.png",
        username="j-doe",
        headline="Software Engineer",
        website="https://example.com",
        about=("Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the "
               "industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type "
               "and scrambled it to make a type specimen book. It has survived not only five centuries, but also the "
               "leap into electronic typesetting, remaining essentially unchanged. It was popularised in the 1960s "
               "with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desktop "
               "publishing software like Aldus PageMaker including versions of Lorem Ipsum."),
        address="1600 Pennsylvania Ave NW, Washington, DC 20500"
    )
    update_user(root_user, update_user_dto, root_user, req)
    user_token3 = get_dummy_user_token(sub="p3", email="test3@example.com")
    user3 = upsert_user_by_user_token(user_token3)
    created_users.append(user3)
    update_user(user3, UpdateUserDTO(
        name=unique_user_name(),
        avatar_action="delete",
    ), root_user, req)
    user_token4 = get_dummy_user_token(sub="p4", email="test4@example.com")
    user4 = upsert_user_by_user_token(user_token4)
    created_users.append(user4)
    update_user(user4, UpdateUserDTO(
        name=unique_user_name(),
        avatar_action="replace",
        image_filename="5b027ec7-c018-4744-9eda-00abf75cf685_1111x712.png",
    ), root_user, req)
    user4.image_filename = "5b027ec7-c018-4744-9eda-00abf75cf685_1111x712.png"
    create_tag_subscription(TagSubscriptionDTO(tags=["observability"]), root_user)
    create_tag_subscription(TagSubscriptionDTO(tags=["event-driven"]), user3)
    create_tag_subscription(TagSubscriptionDTO(tags=["databases", "reliability"]), user4)

    prompts = [
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Message Queues Explained: Producers, Consumers, and Brokers"),
            tags=random_prompt_tags()
        ),
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Event-Driven Architecture: Connecting Services with Events"),
            tags=random_prompt_tags()
        ),
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Designing Reliable Distributed Systems"),
            tags=random_prompt_tags()
        ),
    ]
    for prompt in prompts:
        created_prompt = create_prompt(prompt, root_user)
        update_prompt_status(created_prompt, UpdatePromptStatusDTO(status=PromptStatus.PUBLISHED), root_user, req)
        created_prompts.append(created_prompt)
    user_token2 = get_dummy_user_token(sub="p2", email="test2@example.com", name=unique_user_name())
    user2 = upsert_user_by_user_token(user_token2)
    created_users.append(user2)
    update_user(user2, UpdateUserDTO(
        name=user2.name,
        avatar_action="delete",
    ), root_user, req)
    prompts = [
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Scaling Systems: From a Single Service to a Platform"),
            tags=random_prompt_tags()
        ),
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Distributed systems fixture prompt"),
            tags=random_prompt_tags()
        ),
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Platform architecture fixture prompt"),
            tags=random_prompt_tags()
        ),
    ]
    for prompt in prompts:
        created_prompt = create_prompt(prompt, user2)
        update_prompt_status(created_prompt, UpdatePromptStatusDTO(status=PromptStatus.PUBLISHED), root_user, req)
        created_prompts.append(created_prompt)

    # Add enough published prompts to exercise sitemap generation with a larger dataset.
    for prompt_index in range(len(created_prompts), 75):
        generated_prompt = create_prompt(PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Generated fixture prompt"),
            tags=random_prompt_tags(),
        ), root_user)
        update_prompt_status(
            generated_prompt,
            UpdatePromptStatusDTO(status=PromptStatus.PUBLISHED),
            root_user,
            req,
        )
        created_prompts.append(generated_prompt)

    for tag_name, image_filename in [("distributed-systems", "45e97e68-a321-4657-9956-e942d9d757a7_1279x518.png"),
                                     ("event-driven", "a167891d-7e91-40d6-a5c4-1a3ddb27dcc2_1575x842.png") ]:
        tag = find_tag(tag_name)
        update_tag(tag, UpdateTagDTO(
            name=tag_name,
            image_action="replace",
            image_filename=image_filename,
        ), root_user, req)
        tag.image_filename = image_filename

    comment_texts = [
        "This helped clarify the trade-offs. Thanks for writing it.",
        "Good walkthrough. I would like to see more examples around scaling this design.",
        "The section about operational limits is especially useful.",
        "Nice prompt. The diagrams and constraints make the approach easier to follow.",
    ]
    for prompt_index, prompt in enumerate(created_prompts):
        commenters = [user for user in created_users if user.id != prompt.owner_id]
        for comment_index, user in enumerate(commenters[:2]):
            text = comment_texts[(prompt_index + comment_index) % len(comment_texts)]
            create_prompt_comment(prompt, PromptCommentDTO(text=text), user, req)

    # Seed prompt feedback through the same impression flow used by the API.
    # Each prompt gets a random, unique subset of the available users as voters.
    for prompt in created_prompts:
        voters = random.sample(created_users, k=random.randint(0, len(created_users)))
        for user in voters:
            update_prompt_impression(prompt, UpdatePromptImpressionDTO(
                action=random.choice([
                    PromptImpressionAction.LIKE,
                    PromptImpressionAction.DISLIKE,
                ])), user, req)

    for user in created_users:
        for user2 in created_users:
            if user.id != user2.id:
                update_user_impression(user, UpdateUserImpressionDTO(
                    action=UserImpressionAction.FOLLOW if random.random() < .5 else UserImpressionAction.BLOCK), user2,
                                       req)
    unpublished_prompts = [
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Unpublished fixture prompt"),
            tags=random_prompt_tags()
        ),
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Unpublished fixture prompt"),
            tags=random_prompt_tags()
        ),
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Unpublished fixture prompt"),
            tags=random_prompt_tags()
        ),
    ]
    for prompt in unpublished_prompts:
        create_prompt(prompt, user2)
    rejected_prompts = [
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Rejected fixture prompt"),
            tags=random_prompt_tags()
        ),
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Rejected fixture prompt"),
            tags=random_prompt_tags()
        ),
        PromptDTO(
            title=unique_prompt_title(),
            content=random_prompt_content("Rejected fixture prompt"),
            tags=random_prompt_tags()
        ),
    ]
    for prompt in rejected_prompts:
        created_prompt = create_prompt(prompt, user3)
        update_prompt_status(created_prompt,
                              UpdatePromptStatusDTO(status=PromptStatus.REJECTED, comment="Some rejection reason"),
                              root_user, req)


if __name__ == "__main__":
    create_dummy_fixtures()
