-- 1. Function create account for new Auth user
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.users (
        user_id,
        name,
        email,
        role
    )
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data ->> 'name', ''),
        NEW.email,
        'peer_educator'
    );

    RETURN NEW;
END;
$$;

-- 2. delete any existed trigger
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

-- 3. run function after Auth being created
CREATE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users
FOR EACH ROW
EXECUTE FUNCTION public.handle_new_user();